<?php

defined( 'ABSPATH' ) || exit;

final class Therese_Sync_Plugin {
    public static function init(): void {
        Therese_Sync_Auth::install_header_fix();
        add_action( 'admin_menu', array( 'Therese_Sync_Settings', 'register_menu' ) );
        add_action( 'admin_init', array( 'Therese_Sync_Settings', 'register' ) );
        add_action( 'wp_ajax_therese_sync_targets', array( 'Therese_Sync_Settings', 'ajax_targets' ) );
        add_action( 'rest_api_init', array( 'Therese_Sync_REST', 'register_routes' ) );
    }
}
