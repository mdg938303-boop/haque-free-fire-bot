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


class PromoCodeInvalidError(AppError):
    code = "PROMO_INVALID"
    user_message = "❌ প্রোমো কোডটি সঠিক নয় বা মেয়াদ শেষ হয়ে গেছে।"


class PromoCodeExhaustedError(AppError):
    code = "PROMO_EXHAUSTED"
    user_message = "❌ এই প্রোমো কোডটির ব্যবহারসীমা শেষ হয়ে গেছে।"


class PromoCodeAlreadyUsedError(AppError):
    code = "PROMO_ALREADY_USED"
    user_message = "❌ আপনি এই প্রোমো কোডটি আগেই ব্যবহার করেছেন।"


class PromoCodeMinOrderError(AppError):
    code = "PROMO_MIN_ORDER"
    user_message = "❌ এই প্রোমো কোড ব্যবহারের জন্য ন্যূনতম অর্ডার মূল্য পূরণ হয়নি।"


class InsufficientPointsError(AppError):
    code = "INSUFFICIENT_POINTS"
    user_message = "❌ আপনার পর্যাপ্ত লয়্যালটি পয়েন্ট নেই।"


class OrderNotCancelableError(AppError):
    code = "ORDER_NOT_CANCELABLE"
    user_message = "❌ এই অর্ডারটি এখন আর বাতিল করা যাবে না (হয় সময় পার হয়ে গেছে, নয়তো ইতিমধ্যে সম্পন্ন/বাতিল হয়ে গেছে)।"


class ReviewNotAllowedError(AppError):
    code = "REVIEW_NOT_ALLOWED"
    user_message = "❌ শুধু সম্পন্ন হওয়া অর্ডারের জন্য রেটিং দেওয়া যায়।"


class ResellerAuthError(AppError):
    code = "RESELLER_AUTH_ERROR"
    user_message = "❌ ইউজারনেম বা পাসওয়ার্ড ভুল। /start দিয়ে আবার চেষ্টা করুন।"


class ResellerAlreadyBoundError(AppError):
    code = "RESELLER_ALREADY_BOUND"
    user_message = "❌ এই তথ্য ইতিমধ্যে অন্য একটি Telegram অ্যাকাউন্টে ব্যবহৃত হয়েছে।"


class ResellerRevokedError(AppError):
    code = "RESELLER_REVOKED"
    user_message = "❌ আপনার Reseller অ্যাকাউন্টটি নিষ্ক্রিয় করা হয়েছে। Admin-এর সাথে যোগাযোগ করুন।"


class ResellerUsernameTakenError(AppError):
    code = "RESELLER_USERNAME_TAKEN"
    user_message = "❌ এই ইউজারনেম আগে থেকেই ব্যবহৃত হচ্ছে, অন্য একটা দিন।"


class ResellerPriceNotSetError(AppError):
    code = "RESELLER_PRICE_NOT_SET"
    user_message = "❌ এই প্যাকেজের জন্য আপনার Reseller মূল্য এখনো নির্ধারণ করা হয়নি। Admin-এর সাথে যোগাযোগ করুন।"
