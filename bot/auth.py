from typing import Optional, Dict


def is_allowed_to_create(user: Optional[Dict]) -> bool:
    """Return True if the user dict indicates permission to create meetings.

    Rules:
    - If user is None => False
    - Allowed roles: 'owner', 'admin'
    - Legacy: Allowed statuses 'whitelisted' and 'approve' for backward compatibility
    """
    if not user:
        return False
    status = user.get('status')
    role = user.get('role')
    allowed_roles = ('owner', 'admin')
    allowed_statuses = ('whitelisted', 'approve')
    return (role in allowed_roles) or (status in allowed_statuses)

def is_owner_or_admin(user: Optional[Dict]) -> bool:
    """Return True if the user dict indicates permission to create meetings.

    Rules:
    - If user is None => False
    - Allowed roles: 'owner', 'admin'
    - Legacy: Allowed statuses 'whitelisted' and 'approve' for backward compatibility
    """
    if not user:
        return False
    status = user.get('status')
    role = user.get('role')
    allowed_roles = ('owner', 'admin')
    allowed_statuses = ('whitelisted', 'approve')
    return (role in allowed_roles) and (status in allowed_statuses)


def is_registered_user(user: Optional[Dict]) -> bool:
    """Return True if the user is registered and not banned or pending.
    
    Rules:
    - If user is None => False
    - Allowed if status not in ('pending', 'banned')
    - This allows 'user', 'admin', 'owner' with any valid status except pending/banned
    """
    if not user:
        return False
    status = user.get('status')
    return status not in ('pending', 'banned')