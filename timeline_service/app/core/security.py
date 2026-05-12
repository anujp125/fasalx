from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import httpx
import json
import logging
from typing import Dict, Any
from app.core.config import settings

logger = logging.getLogger(__name__)
security = HTTPBearer()

async def get_redis_client():
    import redis.asyncio as redis
    return redis.from_url(settings.REDIS_URL, decode_responses=True)

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    """
    Service Mesh Auth Interceptor.
    Extracts the JWT and verifies it by calling the main fasalx-auth service.
    Uses Redis caching to avoid network chatter on every request.
    """
    token = credentials.credentials
    redis_client = await get_redis_client()
    cache_key = f"auth_token:{token}"
    
    # 1. Check Redis Cache First
    try:
        cached_user = await redis_client.get(cache_key)
        if cached_user:
            return json.loads(cached_user)
    except Exception as e:
        logger.warning(f"Redis cache error during auth: {e}")

    # 2. Call Auth Service via Mesh
    try:
        async with httpx.AsyncClient() as client:
            headers = {"Authorization": f"Bearer {token}"}
            response = await client.get(
                f"{settings.AUTH_SERVICE_URL}{settings.API_V1_STR}/users/me",
                headers=headers,
                timeout=3.0
            )
            
            if response.status_code == 200:
                user_data = response.json()
                
                # 3. Cache the valid token result for 5 minutes
                try:
                    await redis_client.setex(cache_key, 300, json.dumps(user_data))
                except Exception as e:
                    pass
                    
                return user_data
            else:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired token",
                )
    except httpx.RequestError as e:
        logger.error(f"Failed to communicate with Auth Service: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth service unreachable",
        )
