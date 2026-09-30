=== THERESE Sync ===
Contributors: ieecr
Requires at least: 6.2
Tested up to: 6.8
Requires PHP: 8.0
Stable tag: 1.0.0
License: GPLv2 or later

REST API so THERESE can publish staff posts. Application Passwords over HTTPS only.

== Description ==

Install this plugin on the Strato WordPress site. Then:

1. Settings → THERESE Sync
2. Choose the staff post type
3. Map API parameters to native or ACF fields
4. Whitelist the WordPress user THERESE will use
5. Create an application password for that user (Users → Profile)

Base URL: `/wp-json/therese/v1/`

Authentication: HTTPS Basic Auth with WordPress username + application password.

Endpoints:

* GET `/status`
* GET `/posts` — list posttitle, name, published
* GET `/posts?posttitle=` — all mapped fields
* GET `/posts/exists?name=`
* POST `/posts` — create published post (multipart field `picture` for the image)
* POST `/posts/update` — update by posttitle; optional `new_posttitle` to rename
* POST `/posts/unpublish` — set draft
* POST `/posts/delete` — move to trash

posttitle is unique (employee number + name, built by THERESE). Duplicate name is rejected.

`address` is multiline (newlines preserved). Map it to a textarea, post content, or equivalent ACF field.

If Strato returns 401, pass the Authorization header through to PHP (CGI often strips it).
