import aiohttp
import json
import os
from typing import Optional, Dict, Any
from config import settings
import logging

logger = logging.getLogger(__name__)


class ShortenerError(RuntimeError):
	pass


class DynamicShortener:
	"""Dynamic shortener that loads providers from configuration"""

	def __init__(self, config_file: Optional[str] = None):
		if config_file is None:
			config_file = os.path.join(settings.DATA_DIR, "shorteners.json")
		self.config_file = config_file
		self.providers: Dict[str, Dict[str, Any]] = {}
		self.default_provider = "tinyurl"
		self.fallback_provider = "tinyurl"
		self._load_config()

	def _load_config(self):
		"""Load provider configurations from JSON file"""
		try:
			config_file_to_use = self.config_file
			
			if os.path.exists(config_file_to_use):
				with open(config_file_to_use, 'r', encoding='utf-8') as f:
					config = json.load(f)

				self.providers = config.get('providers', {})
				self.default_provider = config.get('default_provider', 'tinyurl')
				self.fallback_provider = config.get('fallback_provider', 'tinyurl')

				# Filter only enabled providers
				self.providers = {k: v for k, v in self.providers.items() if v.get('enabled', True)}

				logger.info("Loaded %d shortener providers from %s", len(self.providers), self.config_file)
			else:
				logger.warning("Config file %s not found, creating default configuration", self.config_file)
				self._create_default_config()
		except Exception as e:
			logger.error("Failed to load shortener config: %s", e)
			self._create_default_config()

	def _load_builtin_providers(self):
		"""Fallback to built-in providers if config fails"""
		self.providers = {
			"tinyurl": {
				"name": "TinyURL",
				"description": "Free URL shortener with API key",
				"enabled": bool(getattr(settings, 'tinyurl_api_key', None)),
				"api_url": getattr(settings, 'tinyurl_api_url', 'https://api.tinyurl.com/create'),
				"method": "post",
				"headers": {
					"Content-Type": "application/json"
				},
				"body": {
					"url": "{url}"
				},
				"auth": {
					"type": "header",
					"headers": {
						"Authorization": f"Bearer {getattr(settings, 'tinyurl_api_key', '')}"
					}
				},
				"response_type": "json",
				"success_check": "status in (200, 201) and response.get('data', {}).get('tiny_url')",
				"url_extract": "response.get('data', {}).get('tiny_url', '')"
			}
		}
		self.default_provider = "tinyurl"
		self.fallback_provider = "tinyurl"

	def _create_default_config(self):
		"""Create default shorteners.json configuration with environment variables"""
		# Ensure data directory exists
		os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
		
		# Build providers config with env values
		providers = {
			"tinyurl": {
				"name": "TinyURL",
				"description": "Free URL shortener with API key",
				"enabled": bool(getattr(settings, 'tinyurl_api_key', None)),
				"api_url": getattr(settings, 'tinyurl_api_url', 'https://api.tinyurl.com/create'),
				"method": "post",
				"headers": {
					"Content-Type": "application/json"
				},
				"body": {
					"url": "{url}"
				},
				"auth": {
					"type": "header",
					"headers": {
						"Authorization": f"Bearer {getattr(settings, 'tinyurl_api_key', '')}"
					}
				},
				"response_type": "json",
				"success_check": "status in (200, 201) and response.get('data', {}).get('tiny_url')",
				"url_extract": "response.get('data', {}).get('tiny_url', '')"
			},
			"sid": {
				"name": "S.id",
				"description": "Indonesian URL shortener service",
				"enabled": bool(getattr(settings, 'sid_id', None) and getattr(settings, 'sid_key', None)),
				"supports_custom": True,
				"api_url": "https://api.s.id/v1/links",
				"method": "post",
				"headers": {
					"Content-Type": "application/json"
				},
				"auth": {
					"type": "header",
					"headers": {
						"X-Auth-Id": getattr(settings, 'sid_id', ''),
						"X-Auth-Key": getattr(settings, 'sid_key', '')
					}
				},
				"body": {
					"long_url": "{url}"
				},
				"response_type": "json",
				"create_success_check": "response.get('code')==200",
				"id_extract": "response.get('data', {}).get('id', '')",
				"url_extract": "f\"https://s.id/{response.get('data', {}).get('short', '')}\"",
				"update_endpoint": {
					"api_url": "https://api.s.id/v1/links/{id}",
					"method": "post",
					"headers": {
						"Content-Type": "application/json"
					},
					"body": {
						"id": "{id}",
						"short": "{custom}",
						"long_url": "{url}"
					},
					"response_type": "json",
					"success_check": "response.get('code')==200",
					"url_extract": "f\"https://s.id/{response.get('data', {}).get('short', '')}\""
				}
			},
			"bitly": {
				"name": "Bitly",
				"description": "Professional URL shortener service",
				"enabled": bool(getattr(settings, 'bitly_token', None)),
				"api_url": "https://api-ssl.bitly.com/v4/shorten",
				"method": "post",
				"headers": {
					"Authorization": f"Bearer {getattr(settings, 'bitly_token', '')}",
					"Content-Type": "application/json"
				},
				"body": {
					"long_url": "{url}"
				},
				"response_type": "json",
				"success_check": "200<=status<300",
				"url_extract": "response.get('link') or response.get('id')"
			},
			"example_provider": {
				"name": "Example Provider",
				"description": "Example of how to add a new provider with multi-step custom alias support",
				"enabled": False,
				"supports_custom": True,
				"api_url": "https://api.example.com/create",
				"method": "post",
				"headers": {
					"Content-Type": "application/json",
					"Authorization": "Bearer {api_token}"
				},
				"body": {
					"url": "{url}"
				},
				"response_type": "json",
				"create_success_check": "status==200 and response.get('success')==True",
				"url_extract": "response.get('data', {}).get('short_url', '')",
				"update_endpoint": {
					"api_url": "https://api.example.com/update/{id}",
					"method": "post",
					"headers": {
						"Content-Type": "application/json",
						"Authorization": "Bearer {api_token}"
					},
					"body": {
						"id": "{id}",
						"custom_alias": "{custom}"
					},
					"response_type": "json",
					"success_check": "status==200 and response.get('success')==True",
					"url_extract": "response.get('data', {}).get('short_url', '')"
				}
			}
		}
		
		config = {
			"providers": providers,
			"default_provider": "tinyurl",
			"fallback_provider": "tinyurl"
		}
		
		# Save to file
		try:
			with open(self.config_file, 'w', encoding='utf-8') as f:
				json.dump(config, f, indent=2, ensure_ascii=False)
			logger.info("Created default shorteners.json at %s", self.config_file)
		except Exception as e:
			logger.error("Failed to create default shorteners.json: %s", e)
			# Fallback to builtin
			self._load_builtin_providers()
			return
		
		# Load the config
		self.providers = {k: v for k, v in providers.items() if v.get('enabled', True)}
		self.default_provider = config.get('default_provider', 'tinyurl')
		self.fallback_provider = config.get('fallback_provider', 'tinyurl')

	def _format_template(self, template: str, **kwargs) -> str:
		"""Format template string with variables"""
		try:
			return template.format(**kwargs)
		except KeyError as e:
			logger.error("Missing variable in template: %s", e)
			return template

	def _evaluate_condition(self, condition: str, response: Any, status: int) -> bool:
		"""Evaluate success condition"""
		try:
			# Simple evaluation with response and status variables
			local_vars = {'response': response, 'status': status}
			return eval(condition, {"__builtins__": {}}, local_vars)
		except Exception as e:
			logger.error("Failed to evaluate condition '%s': %s", condition, e)
			return False

	def _extract_url(self, extract_expr: str, response: Any, status: int) -> str:
		"""Extract URL from response using expression"""
		try:
			local_vars = {'response': response, 'status': status}
			result = eval(extract_expr, {"__builtins__": {}}, local_vars)
			return str(result) if result else ""
		except Exception as e:
			logger.error("Failed to extract URL with '%s': %s", extract_expr, e)
			return ""

	async def _call_provider(self, provider_config: Dict[str, Any], url: str, custom: Optional[str] = None) -> str:
		"""Call a provider API dynamically, supporting multi-step workflows"""
		if custom and not provider_config.get('supports_custom', False):
			raise ShortenerError(f"{provider_config['name']} does not support custom aliases")

		# Check if this provider supports multi-step workflow (create + update)
		if custom and 'update_endpoint' in provider_config:
			# Multi-step workflow: create first, then update with custom alias
			return await self._call_multi_step_provider(provider_config, url, custom)
		else:
			# Single-step workflow
			return await self._call_single_step_provider(provider_config, url, custom)

	async def _call_single_step_provider(self, provider_config: Dict[str, Any], url: str, custom: Optional[str] = None) -> str:
		"""Single-step API call for providers that support custom alias in one request"""
		logger.debug("_call_single_step_provider: url=%s, custom=%s", url, custom)
		api_url = self._format_template(provider_config['api_url'], url=url, custom=custom or '')

		# Build headers
		headers = provider_config.get('headers', {}).copy()
		if 'auth' in provider_config:
			auth_config = provider_config['auth']
			if auth_config['type'] == 'header':
				for header_name, header_value in auth_config.get('headers', {}).items():
					headers[header_name] = self._format_template(header_value,
						sid_id=getattr(settings, 'sid_id', ''),
						sid_key=getattr(settings, 'sid_key', ''),
						bitly_token=getattr(settings, 'bitly_token', ''))

		# Build request data
		method = provider_config.get('method', 'get').lower()
		request_data = None

		if method == 'post':
			body_config = provider_config.get('body', {})
			if body_config:
				request_data = json.dumps({k: self._format_template(str(v), url=url, custom=custom or '') for k, v in body_config.items()})
				headers['Content-Type'] = 'application/json'
		else:
			# GET method - add params to URL
			params_config = provider_config.get('params', {})
			if params_config:
				from urllib.parse import urlencode
				params = {k: self._format_template(str(v), url=url, custom=custom or '') for k, v in params_config.items()}
				api_url += '?' + urlencode(params)
				logger.debug("GET params: %s", params)

		logger.debug("Calling %s API: %s", provider_config['name'], api_url)

		async with aiohttp.ClientSession() as session:
			try:
				if method == 'post':
					async with session.post(api_url, data=request_data, headers=headers) as resp:
						return await self._process_response(resp, provider_config)
				else:
					async with session.get(api_url, headers=headers) as resp:
						return await self._process_response(resp, provider_config)
			except Exception as e:
				logger.error("API call failed for %s: %s", provider_config['name'], e)
				raise ShortenerError(f"{provider_config['name']} API error: {e}")

	async def _call_multi_step_provider(self, provider_config: Dict[str, Any], url: str, custom: str) -> str:
		"""Multi-step workflow: create link first, then update with custom alias"""
		logger.debug("Starting multi-step workflow for %s with custom alias: %s", provider_config['name'], custom)

		# Step 1: Create the link first (without custom alias)
		create_api_url = self._format_template(provider_config['api_url'], url=url, custom='')

		# Build create headers
		create_headers = provider_config.get('headers', {}).copy()
		if 'auth' in provider_config:
			auth_config = provider_config['auth']
			if auth_config['type'] == 'header':
				for header_name, header_value in auth_config.get('headers', {}).items():
					create_headers[header_name] = self._format_template(header_value,
						sid_id=getattr(settings, 'sid_id', ''),
						sid_key=getattr(settings, 'sid_key', ''),
						bitly_token=getattr(settings, 'bitly_token', ''))

		# Build create request data
		create_method = provider_config.get('method', 'get').lower()
		create_request_data = None

		if create_method == 'post':
			create_body_config = provider_config.get('body', {})
			if create_body_config:
				create_request_data = json.dumps({k: self._format_template(str(v), url=url, custom='') for k, v in create_body_config.items()})
				create_headers['Content-Type'] = 'application/json'

		logger.debug("Create call for %s: %s", provider_config['name'], create_api_url)

		create_response_data = None
		async with aiohttp.ClientSession() as session:
			try:
				if create_method == 'post':
					async with session.post(create_api_url, data=create_request_data, headers=create_headers) as resp:
						create_response_data = await self._process_create_response(resp, provider_config)
				else:
					async with session.get(create_api_url, headers=create_headers) as resp:
						create_response_data = await self._process_create_response(resp, provider_config)
			except Exception as e:
				logger.error("Create API call failed for %s: %s", provider_config['name'], e)
				raise ShortenerError(f"{provider_config['name']} create API error: {e}")

		# Step 2: Update with custom alias using the ID from create response
		update_config = provider_config['update_endpoint'].copy()
		update_config['name'] = provider_config['name']  # Add name for error messages
		id_extract_expr = provider_config.get('id_extract', "response.get('data', {}).get('id') or response.get('id')")
		link_id = self._extract_url(id_extract_expr, create_response_data, 200)
		if not link_id:
			logger.error("Create response missing ID for update: %s", create_response_data)
			# Return the created URL if available
			created_url = create_response_data.get('short_url') or create_response_data.get('url')
			if created_url:
				return created_url
			raise ShortenerError(f"Failed to get link ID from create response for {provider_config['name']}")

		update_url = self._format_template(update_config['api_url'], url=url, custom=custom, id=link_id)

		# Build update headers
		update_headers = update_config.get('headers', {}).copy()
		if 'auth' in provider_config:
			auth_config = provider_config['auth']
			if auth_config['type'] == 'header':
				for header_name, header_value in auth_config.get('headers', {}).items():
					update_headers[header_name] = self._format_template(header_value,
						sid_id=getattr(settings, 'sid_id', ''),
						sid_key=getattr(settings, 'sid_key', ''),
						bitly_token=getattr(settings, 'bitly_token', ''))

		# Build update request data
		update_method = update_config.get('method', 'post').lower()
		update_request_data = None

		if update_method == 'post':
			update_body_config = update_config.get('body', {})
			if update_body_config:
				update_request_data = json.dumps({k: self._format_template(str(v), url=url, custom=custom, id=link_id) for k, v in update_body_config.items()})
				update_headers['Content-Type'] = 'application/json'

		logger.debug("Update call for %s: %s", provider_config['name'], update_url)

		async with aiohttp.ClientSession() as session:
			try:
				if update_method == 'post':
					async with session.post(update_url, data=update_request_data, headers=update_headers) as resp:
						return await self._process_response(resp, update_config)
				else:
					async with session.get(update_url, headers=update_headers) as resp:
						return await self._process_response(resp, update_config)
			except Exception as e:
				logger.error("Update API call failed for %s: %s", provider_config['name'], e)
				# If update fails, return the original created link
				created_url = create_response_data.get('short_url') or create_response_data.get('url')
				if created_url:
					logger.warning("Update failed, returning original link: %s", created_url)
					return created_url
				raise ShortenerError(f"{provider_config['name']} update API error: {e}")

	async def _process_create_response(self, resp: aiohttp.ClientResponse, provider_config: Dict[str, Any]) -> Dict[str, Any]:
		"""Process create response and return data for update step"""
		status = resp.status
		response_type = provider_config.get('response_type', 'text')

		if response_type == 'json':
			response_data = await resp.json()
		else:
			response_data = await resp.text()

		# Check success condition for create
		create_success_check = provider_config.get('create_success_check', provider_config.get('success_check', 'status==200'))
		if not self._evaluate_condition(create_success_check, response_data, status):
			logger.error("%s create returned error %s: %s", provider_config['name'], status, response_data)
			raise ShortenerError(f"{provider_config['name']} create error {status}: {response_data}")

		# Return the response data for use in update step
		return response_data if isinstance(response_data, dict) else {'url': response_data}

	async def _process_response(self, resp: aiohttp.ClientResponse, provider_config: Dict[str, Any]) -> str:
		"""Process API response"""
		status = resp.status
		response_type = provider_config.get('response_type', 'text')

		if response_type == 'json':
			response_data = await resp.json()
		else:
			response_data = await resp.text()

		# Check success condition
		success_check = provider_config.get('success_check', 'status==200')
		if not self._evaluate_condition(success_check, response_data, status):
			logger.error("%s returned error %s: %s", provider_config['name'], status, response_data)
			raise ShortenerError(f"{provider_config['name']} error {status}: {response_data}")

		# Extract URL
		url_extract = provider_config.get('url_extract', 'response')
		result = self._extract_url(url_extract, response_data, status)

		if not result:
			logger.error("Failed to extract URL from %s response", provider_config['name'])
			raise ShortenerError(f"Failed to extract URL from {provider_config['name']} response")

		logger.debug("%s result: %s", provider_config['name'], result)
		return result

	async def shorten(self, url: str, provider: Optional[str] = None, custom: Optional[str] = None) -> str:
		"""Shorten URL using specified or default provider"""
		# Sanitize and validate URL
		url = url.strip() if url else ""
		if not url:
			raise ShortenerError("URL is empty")
		
		if not url.startswith(('http://', 'https://')):
			raise ShortenerError(f"Invalid URL format: {url}")
		
		provider_name = provider or self.default_provider

		if provider_name not in self.providers:
			logger.warning("Provider %s not found, using fallback %s", provider_name, self.fallback_provider)
			provider_name = self.fallback_provider

		if provider_name not in self.providers:
			raise ShortenerError("No available shortener providers")

		provider_config = self.providers[provider_name]
		logger.info("Shortening URL %s with %s", url, provider_config['name'])

		try:
			return await self._call_provider(provider_config, url, custom)
		except ShortenerError:
			# Try fallback if different from current provider
			if provider_name != self.fallback_provider and self.fallback_provider in self.providers:
				logger.warning("Primary provider %s failed, trying fallback %s", provider_name, self.fallback_provider)
				try:
					fallback_config = self.providers[self.fallback_provider]
					return await self._call_provider(fallback_config, url, custom)
				except ShortenerError as e:
					logger.error("Fallback provider also failed: %s", e)

			# Re-raise original error
			raise

	def get_available_providers(self) -> Dict[str, str]:
		"""Get dict of provider_id -> provider_name for UI"""
		return {pid: pconfig['name'] for pid, pconfig in self.providers.items()}

	def reload_config(self):
		"""Reload configuration (useful for runtime updates)"""
		self._load_config()


# Global instance
_shortener = DynamicShortener()


async def make_short(url: str, provider: Optional[str] = None, custom: Optional[str] = None) -> str:
	"""
	Create a short URL using the selected provider.

	provider: optional string provider ID
	Falls back to default provider if specified provider fails.
	"""
	return await _shortener.shorten(url, provider, custom)


def get_available_providers() -> Dict[str, str]:
	"""Get available providers for UI"""
	return _shortener.get_available_providers()


def reload_shortener_config():
	"""Reload shortener configuration"""
	_shortener.reload_config()