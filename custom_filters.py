from pyrogram import filters

add_category_filter = filters.create(lambda _, __, query: query.data == "add_category")
remove_category_filter = filters.create(lambda _, __, query: query.data.startswith("remove_category"))
modify_category_filter = filters.create(lambda _, __, query: query.data.startswith("modify_category"))
category_filter = filters.create(lambda _, __, query: query.data.startswith("category"))
menu_filter = filters.create(lambda _, __, query: query.data.startswith("menu"))
list_filter = filters.create(lambda _, __, query: query.data.startswith("list"))
list_by_status_filter = filters.create(lambda _, __, query: query.data.split("#")[0] == "by_status_list")
add_magnet_filter = filters.create(lambda _, __, query: query.data.startswith("add_magnet"))
add_torrent_filter = filters.create(lambda _, __, query: query.data.startswith("add_torrent"))
pause_all_filter = filters.create(lambda _, __, query: query.data.startswith("pause_all"))
resume_all_filter = filters.create(lambda _, __, query: query.data.startswith("resume_all"))
pause_filter = filters.create(lambda _, __, query: query.data.startswith("pause"))
resume_filter = filters.create(lambda _, __, query: query.data.startswith("resume"))
delete_one_filter = filters.create(lambda _, __, query: query.data.split("#")[0] == "delete_one")
delete_one_no_data_filter = filters.create(lambda _, __, query: query.data.startswith("delete_one_no_data"))
delete_one_data_filter = filters.create(lambda _, __, query: query.data.startswith("delete_one_data"))
delete_all_filter = filters.create(lambda _, __, query: query.data.split("#")[0] == "delete_all")
delete_all_no_data_filter = filters.create(lambda _, __, query: query.data.startswith("delete_all_no_data"))
delete_all_data_filter = filters.create(lambda _, __, query: query.data.startswith("delete_all_data"))
torrentInfo_filter = filters.create(lambda _, __, query: query.data.startswith("torrentInfo"))
select_category_filter = filters.create(lambda _, __, query: query.data.startswith("select_category"))
ngrok_info_filter = filters.create(lambda _, __, query: query.data.startswith("ngrok_info"))
system_info_filter = filters.create(lambda _, __, query: query.data.startswith("system_info"))
extract_file_filter = filters.create(lambda _, __, query: query.data.startswith("extract_file"))
aria_ref_filter = filters.create(lambda _, __, query: query.data.startswith("aria-ref"))
aria_can_filter = filters.create(lambda _, __, query: query.data.startswith("aria-can"))
aria_add_filter = filters.create(lambda _, __, query: query.data.startswith("aria-add"))
aria_ret_filter = filters.create(lambda _, __, query: query.data.startswith("aria-ret"))
