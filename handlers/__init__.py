from aiogram import Router

from . import onboarding, join_requests, post_scheduler, member_updates, broadcast, group_guard

main_router = Router(name="main")
main_router.include_router(onboarding.router)
main_router.include_router(join_requests.router)
main_router.include_router(member_updates.router)
main_router.include_router(post_scheduler.router)
main_router.include_router(broadcast.router)
main_router.include_router(group_guard.router)  # eng oxirida — boshqa handlerlar ishlamagan xabarlarni "ushlaydi"