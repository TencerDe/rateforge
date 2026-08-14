from .models import IdentityType, RateLimitContext


class IdentityResolver:
    @staticmethod
    def resolve(
        context: RateLimitContext,
        identity_type: IdentityType,
    ) -> str:
        value = {
            IdentityType.IP: context.ip,
            IdentityType.USER: context.user_id,
            IdentityType.API_KEY: context.api_key,
            IdentityType.PLAN: context.plan,
        }.get(identity_type)

        if value is None:
            raise ValueError(
                f"No value available for identity type: {identity_type.value}"
            )

        return f"{identity_type.value}:{value}"