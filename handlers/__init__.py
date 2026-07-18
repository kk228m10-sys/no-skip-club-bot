from aiogram import Dispatcher

from . import onboarding, menu, training, materials, nutrition, booking, admin, settings, ai_psychologist, verification
from .blocking import BlockCheckMiddleware


def register_all_handlers(dp: Dispatcher):
    # Блокировка проверяется раньше любого хендлера, включая /start.
    dp.message.outer_middleware(BlockCheckMiddleware())
    dp.callback_query.outer_middleware(BlockCheckMiddleware())

    dp.include_router(admin.router)
    dp.include_router(onboarding.router)
    dp.include_router(menu.router)
    dp.include_router(settings.router)
    dp.include_router(training.router)
    dp.include_router(verification.router)
    dp.include_router(materials.router)
    dp.include_router(nutrition.router)
    dp.include_router(booking.router)
    dp.include_router(ai_psychologist.router)
