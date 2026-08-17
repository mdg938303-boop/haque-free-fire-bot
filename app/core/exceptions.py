class AppError(Exception):
    """Base error. `user_message` is safe to show to Telegram users (in Bangla).
    `internal_detail` is only ever logged / shown in the Admin Panel."""

    code = "SERVICE_ERROR"
    user_message = "দুঃখিত, একটি সমস্যা হয়েছে। কিছুক্ষণ পর আবার চেষ্টা করুন।"

    def __init__(self, internal_detail: str = "", user_message: str | None = None, code: str | None = None):
        self.internal_detail = internal_detail
        if user_message:
            self.user_message = user_message
        if code:
            self.code = code
        super().__init__(internal_detail or self.user_message)


class ValidationError(AppError):
    code = "VALIDATION_ERROR"
    user_message = "❌ UID যাচাই করা যায়নি। সঠিক UID দিয়ে আবার চেষ্টা করুন।"


class ValidationRequiredError(AppError):
    code = "VALIDATION_REQUIRED"
    user_message = "⚠️ অর্ডার করার আগে UID যাচাই করা আবশ্যক।"


class InsufficientBalanceError(AppError):
    code = "INSUFFICIENT_FUNDS"
    user_message = "❌ আপনার ব্যালেন্স পর্যাপ্ত নয়।"


class IdempotencyConflictError(AppError):
    code = "IDEMPOTENCY_CONFLICT"
    user_message = "⚠️ এই অর্ডারটি ইতিমধ্যে প্রক্রিয়াধীন। একই অনুরোধ একাধিকবার পাঠাবেন না।"


class SecurityError(AppError):
    code = "SECURITY_ERROR"
    user_message = "❌ অনুরোধটি যাচাই করা যায়নি।"


class ServiceDisabledError(AppError):
    code = "SERVICE_DISABLED"
    user_message = "⚠️ এই মুহূর্তে সেবাটি বন্ধ আছে। কিছুক্ষণ পর আবার চেষ্টা করুন।"


class OrderNotFoundError(AppError):
    code = "ORDER_NOT_FOUND"
    user_message = "❌ অর্ডারটি খুঁজে পাওয়া যায়নি।"


class PackageInactiveError(AppError):
    code = "PACKAGE_INACTIVE"
    user_message = "❌ প্যাকেজটি বর্তমানে বন্ধ আছে।"


class ProviderUnavailableError(AppError):
    code = "PROVIDER_UNAVAILABLE"
    user_message = "⚠️ সাময়িক প্রযুক্তিগত সমস্যা হয়েছে। কিছুক্ষণ পর আবার চেষ্টা করুন।"
