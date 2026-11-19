from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.core.database import SessionDep
from app.core.security import create_access_token
from app.modules.users import services
from app.modules.users.dependencies import CurrentUser
from app.modules.users.schemas import Token, UserCreate, UserRead

router = APIRouter(tags=["users"])


@router.post(
    "/auth/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
)
async def register(data: UserCreate, session: SessionDep):
    try:
        return await services.create_user(session, data)
    except services.EmailAlreadyRegisteredError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        ) from None


@router.post("/auth/login", response_model=Token)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: SessionDep,
):
    user = await services.authenticate_user(
        session, form_data.username, form_data.password
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Token(access_token=create_access_token(user.id))


@router.get("/users/me", response_model=UserRead)
async def read_me(current_user: CurrentUser):
    return current_user