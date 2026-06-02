def is_admin(user_id, settings):
    return user_id in settings.admin_user_ids
