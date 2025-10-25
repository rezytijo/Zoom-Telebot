import asyncio
import json
from zoom import zoom_client

async def main():
    try:
        info = await zoom_client.fetch_token_info()
    except Exception as e:
        print("Error fetching token info:", e)
        return

    print("Token endpoint status:", info.get('status'))
    print("Requested data:", info.get('requested_data'))
    print("Response JSON:")
    print(json.dumps(info.get('json'), indent=2, ensure_ascii=False))
    print("Raw text:\n", info.get('text'))

if __name__ == '__main__':
    asyncio.run(main())
