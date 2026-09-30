<?php

defined( 'ABSPATH' ) || exit;

final class Therese_Sync_Auth {
    public static function install_header_fix(): void {
        if ( empty( $_SERVER['HTTP_AUTHORIZATION'] ) ) {
            if ( ! empty( $_SERVER['REDIRECT_HTTP_AUTHORIZATION'] ) ) {
                $_SERVER['HTTP_AUTHORIZATION'] = $_SERVER['REDIRECT_HTTP_AUTHORIZATION'];
            } elseif ( ! empty( $_SERVER['HTTP_X_AUTHORIZATION'] ) ) {
                $_SERVER['HTTP_AUTHORIZATION'] = $_SERVER['HTTP_X_AUTHORIZATION'];
            }
        }
        if ( empty( $_SERVER['PHP_AUTH_USER'] ) && ! empty( $_SERVER['HTTP_AUTHORIZATION'] )
            && 0 === stripos( (string) $_SERVER['HTTP_AUTHORIZATION'], 'basic ' ) ) {
            $decoded = base64_decode( substr( (string) $_SERVER['HTTP_AUTHORIZATION'], 6 ), true );
            if ( is_string( $decoded ) && str_contains( $decoded, ':' ) ) {
                list( $_SERVER['PHP_AUTH_USER'], $_SERVER['PHP_AUTH_PW'] ) = explode( ':', $decoded, 2 );
            }
        }
    }

    public static function is_https(): bool {
        if ( function_exists( 'is_ssl' ) && is_ssl() ) {
            return true;
        }
        $forwarded = strtolower( (string) ( $_SERVER['HTTP_X_FORWARDED_PROTO'] ?? '' ) );
        return $forwarded === 'https';
    }

    public static function require_https(): bool {
        $local = defined( 'WP_ENVIRONMENT_TYPE' ) && WP_ENVIRONMENT_TYPE === 'local';
        return (bool) apply_filters( 'therese_sync_require_https', ! $local );
    }

    public static function permission( WP_REST_Request $request ) {
        unset( $request );
        if ( self::require_https() && ! self::is_https() ) {
            return new WP_Error(
                'therese_sync_https',
                'HTTPS is required.',
                array( 'status' => 403 )
            );
        }
        $app_password = function_exists( 'rest_get_authenticated_app_password' )
            ? rest_get_authenticated_app_password()
            : null;
        if ( ! $app_password ) {
            return new WP_Error(
                'therese_sync_app_password',
                'Username and application password required.',
                array( 'status' => 401 )
            );
        }
        $user = wp_get_current_user();
        if ( ! $user || ! $user->ID ) {
            return new WP_Error(
                'therese_sync_auth',
                'Invalid username or application password.',
                array( 'status' => 401 )
            );
        }
        if ( ! Therese_Sync_Settings::user_is_allowed( (int) $user->ID ) ) {
            return new WP_Error(
                'therese_sync_forbidden',
                'This WordPress user is not allowed to use the THERESE API.',
                array( 'status' => 403 )
            );
        }
        return true;
    }
}
