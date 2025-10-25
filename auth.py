from typing import Optional, Dict


def is_allowed_to_create(user: Optional[Dict]) -> bool:
    """Return True if the user dict indicates permission to create meetings.

    Rules:
    - If user is None => False
    - Allowed statuses: 'whitelisted' and legacy 'approve'
    - Role 'owner' is always allowed
    """
    if not user:
        return False
    status = user.get('status')
    role = user.get('role')
    allowed_statuses = ('whitelisted', 'approve')
    return (status in allowed_statuses) or (role == 'owner')
