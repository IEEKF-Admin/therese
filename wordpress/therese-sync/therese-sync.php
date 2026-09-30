<?php
/**
 * Plugin Name: THERESE Sync
 * Description: REST API so THERESE can create, update and remove staff posts.
 * Version: 1.0.0
 * Requires at least: 6.2
 * Requires PHP: 8.0
 * Author: IEECR
 * Text Domain: therese-sync
 */

defined( 'ABSPATH' ) || exit;

define( 'THERESE_SYNC_VERSION', '1.0.0' );
define( 'THERESE_SYNC_FILE', __FILE__ );
define( 'THERESE_SYNC_DIR', plugin_dir_path( __FILE__ ) );

require_once THERESE_SYNC_DIR . 'includes/class-auth.php';
require_once THERESE_SYNC_DIR . 'includes/class-fields.php';
require_once THERESE_SYNC_DIR . 'includes/class-settings.php';
require_once THERESE_SYNC_DIR . 'includes/class-rest.php';
require_once THERESE_SYNC_DIR . 'includes/class-plugin.php';

Therese_Sync_Plugin::init();
