<?php

defined( 'ABSPATH' ) || exit;

final class Therese_Sync_REST {
    public const NS = 'therese/v1';

    public static function register_routes(): void {
        $auth = array( 'Therese_Sync_Auth', 'permission' );
        register_rest_route( self::NS, '/status', array(
            'methods'             => 'GET',
            'callback'            => array( self::class, 'status' ),
            'permission_callback' => $auth,
        ) );
        register_rest_route( self::NS, '/posts', array(
            array(
                'methods'             => 'GET',
                'callback'            => array( self::class, 'get_or_list' ),
                'permission_callback' => $auth,
            ),
            array(
                'methods'             => 'POST',
                'callback'            => array( self::class, 'create' ),
                'permission_callback' => $auth,
            ),
        ) );
        register_rest_route( self::NS, '/posts/exists', array(
            'methods'             => 'GET',
            'callback'            => array( self::class, 'exists' ),
            'permission_callback' => $auth,
        ) );
        register_rest_route( self::NS, '/posts/update', array(
            'methods'             => 'POST',
            'callback'            => array( self::class, 'update' ),
            'permission_callback' => $auth,
        ) );
        register_rest_route( self::NS, '/posts/unpublish', array(
            'methods'             => 'POST',
            'callback'            => array( self::class, 'unpublish' ),
            'permission_callback' => $auth,
        ) );
        register_rest_route( self::NS, '/posts/delete', array(
            'methods'             => 'POST',
            'callback'            => array( self::class, 'delete' ),
            'permission_callback' => $auth,
        ) );
    }

    public static function status() {
        $settings = Therese_Sync_Settings::get();
        return rest_ensure_response( array(
            'ok'        => true,
            'post_type' => $settings['post_type'],
            'mapped'    => array_keys( array_filter( $settings['map'] ) ),
        ) );
    }

    public static function get_or_list( WP_REST_Request $request ) {
        $posttitle = trim( (string) $request->get_param( 'posttitle' ) );
        if ( $posttitle !== '' ) {
            return self::get_one( $posttitle );
        }
        $error = self::configured();
        if ( is_wp_error( $error ) ) {
            return $error;
        }
        $settings = Therese_Sync_Settings::get();
        $query = new WP_Query( array(
            'post_type'      => $settings['post_type'],
            'post_status'    => array( 'publish', 'draft', 'pending', 'private', 'future' ),
            'posts_per_page' => -1,
            'orderby'        => 'title',
            'order'          => 'ASC',
        ) );
        $name_target = (string) ( $settings['map']['name'] ?? '' );
        $items = array();
        foreach ( $query->posts as $post ) {
            $items[] = array(
                'posttitle' => (string) $post->post_title,
                'name'      => $name_target ? Therese_Sync_Fields::read( (int) $post->ID, array( 'name' => $name_target ) )['name'] : null,
                'published' => $post->post_status === 'publish',
            );
        }
        return rest_ensure_response( array( 'posts' => $items ) );
    }

    public static function exists( WP_REST_Request $request ) {
        $error = self::configured();
        if ( is_wp_error( $error ) ) {
            return $error;
        }
        $name = self::param( $request, 'name' );
        if ( $name === '' ) {
            return self::fail( 'therese_sync_name', 'name is required.', 400 );
        }
        $settings = Therese_Sync_Settings::get();
        $target = (string) ( $settings['map']['name'] ?? '' );
        if ( $target === '' ) {
            return self::fail( 'therese_sync_map', 'name is not mapped.', 400 );
        }
        $ids = Therese_Sync_Fields::find_by_name( $settings['post_type'], $target, $name );
        if ( count( $ids ) > 1 ) {
            return self::fail( 'therese_sync_conflict', 'name already exists more than once.', 409 );
        }
        $posttitle = null;
        if ( $ids ) {
            $post = get_post( $ids[0] );
            $posttitle = $post ? (string) $post->post_title : null;
        }
        return rest_ensure_response( array(
            'exists'    => (bool) $ids,
            'posttitle' => $posttitle,
        ) );
    }

    public static function create( WP_REST_Request $request ) {
        $error = self::configured();
        if ( is_wp_error( $error ) ) {
            return $error;
        }
        $settings = Therese_Sync_Settings::get();
        $posttitle = self::param( $request, 'posttitle' );
        if ( $posttitle === '' ) {
            return self::fail( 'therese_sync_posttitle', 'posttitle is required.', 400 );
        }
        if ( Therese_Sync_Fields::find_by_posttitle( $settings['post_type'], $posttitle ) ) {
            return self::fail( 'therese_sync_conflict', 'posttitle already exists.', 409 );
        }
        $name = self::param( $request, 'name' );
        $name_error = self::reject_duplicate_name( $settings, $name, 0 );
        if ( is_wp_error( $name_error ) ) {
            return $name_error;
        }
        $post_id = wp_insert_post( array(
            'post_type'   => $settings['post_type'],
            'post_title'  => $posttitle,
            'post_status' => 'publish',
        ), true );
        if ( is_wp_error( $post_id ) ) {
            $post_id->add_data( array( 'status' => 500 ) );
            return $post_id;
        }
        $picture = self::handle_picture( $request, (int) $post_id );
        if ( is_wp_error( $picture ) ) {
            wp_delete_post( (int) $post_id, true );
            return $picture;
        }
        Therese_Sync_Fields::apply( (int) $post_id, $settings['map'], self::payload( $request ), $picture );
        return rest_ensure_response( self::payload_for_post( (int) $post_id ) );
    }

    public static function update( WP_REST_Request $request ) {
        $found = self::post_from_request( $request );
        if ( is_wp_error( $found ) ) {
            return $found;
        }
        $settings = Therese_Sync_Settings::get();
        $post = $found;
        $name = self::has_param( $request, 'name' ) ? self::param( $request, 'name' ) : null;
        if ( $name !== null ) {
            $name_error = self::reject_duplicate_name( $settings, $name, (int) $post->ID );
            if ( is_wp_error( $name_error ) ) {
                return $name_error;
            }
        }
        $new_title = self::param( $request, 'new_posttitle' );
        $post_update = array( 'ID' => (int) $post->ID );
        if ( $new_title !== '' && $new_title !== $post->post_title ) {
            if ( Therese_Sync_Fields::find_by_posttitle( $settings['post_type'], $new_title ) ) {
                return self::fail( 'therese_sync_conflict', 'posttitle already exists.', 409 );
            }
            $post_update['post_title'] = $new_title;
        }
        wp_update_post( $post_update );
        $picture = self::handle_picture( $request, (int) $post->ID );
        if ( is_wp_error( $picture ) ) {
            return $picture;
        }
        Therese_Sync_Fields::apply( (int) $post->ID, $settings['map'], self::payload( $request ), $picture );
        return rest_ensure_response( self::payload_for_post( (int) $post->ID ) );
    }

    public static function unpublish( WP_REST_Request $request ) {
        $post = self::post_from_request( $request );
        if ( is_wp_error( $post ) ) {
            return $post;
        }
        wp_update_post( array(
            'ID'          => (int) $post->ID,
            'post_status' => 'draft',
        ) );
        return rest_ensure_response( self::payload_for_post( (int) $post->ID ) );
    }

    public static function delete( WP_REST_Request $request ) {
        $post = self::post_from_request( $request );
        if ( is_wp_error( $post ) ) {
            return $post;
        }
        $trashed = wp_trash_post( (int) $post->ID );
        if ( ! $trashed ) {
            return self::fail( 'therese_sync_delete', 'Could not move the post to trash.', 500 );
        }
        return rest_ensure_response( array(
            'ok'        => true,
            'posttitle' => (string) $post->post_title,
            'trashed'   => true,
        ) );
    }

    private static function get_one( string $posttitle ) {
        $post = self::find_one_by_posttitle( $posttitle );
        if ( is_wp_error( $post ) ) {
            return $post;
        }
        return rest_ensure_response( self::payload_for_post( (int) $post->ID ) );
    }

    private static function configured() {
        $settings = Therese_Sync_Settings::get();
        if ( $settings['post_type'] === '' ) {
            return self::fail( 'therese_sync_config', 'No post type is configured.', 400 );
        }
        return null;
    }

    private static function post_from_request( WP_REST_Request $request ) {
        $error = self::configured();
        if ( is_wp_error( $error ) ) {
            return $error;
        }
        $posttitle = self::param( $request, 'posttitle' );
        if ( $posttitle === '' ) {
            return self::fail( 'therese_sync_posttitle', 'posttitle is required.', 400 );
        }
        return self::find_one_by_posttitle( $posttitle );
    }

    private static function find_one_by_posttitle( string $posttitle ) {
        $settings = Therese_Sync_Settings::get();
        $ids = Therese_Sync_Fields::find_by_posttitle( $settings['post_type'], $posttitle );
        if ( ! $ids ) {
            return self::fail( 'therese_sync_not_found', 'No post with this posttitle.', 404 );
        }
        if ( count( $ids ) > 1 ) {
            return self::fail( 'therese_sync_conflict', 'posttitle already exists more than once.', 409 );
        }
        $post = get_post( $ids[0] );
        if ( ! $post ) {
            return self::fail( 'therese_sync_not_found', 'No post with this posttitle.', 404 );
        }
        return $post;
    }

    private static function reject_duplicate_name( array $settings, string $name, int $except_id ) {
        $target = (string) ( $settings['map']['name'] ?? '' );
        if ( $name === '' || $target === '' ) {
            return null;
        }
        $ids = Therese_Sync_Fields::find_by_name( $settings['post_type'], $target, $name );
        foreach ( $ids as $id ) {
            if ( (int) $id !== $except_id ) {
                return self::fail( 'therese_sync_conflict', 'name already exists.', 409 );
            }
        }
        return null;
    }

    private static function payload_for_post( int $post_id ): array {
        $post = get_post( $post_id );
        $settings = Therese_Sync_Settings::get();
        $fields = Therese_Sync_Fields::read( $post_id, $settings['map'] );
        return array_merge(
            array(
                'id'        => $post_id,
                'posttitle' => $post ? (string) $post->post_title : '',
                'published' => $post && $post->post_status === 'publish',
            ),
            $fields
        );
    }

    private static function payload( WP_REST_Request $request ): array {
        $out = array();
        foreach ( Therese_Sync_Fields::PARAMS as $param ) {
            if ( $param === 'picture' ) {
                continue;
            }
            if ( self::has_param( $request, $param ) ) {
                $out[ $param ] = self::param( $request, $param );
            }
        }
        return $out;
    }

    private static function has_param( WP_REST_Request $request, string $key ): bool {
        $params = $request->get_params();
        return array_key_exists( $key, $params ) || array_key_exists( ucfirst( $key ), $params );
    }

    private static function param( WP_REST_Request $request, string $key ): string {
        $value = $request->get_param( $key );
        if ( $value === null && $key === 'name' ) {
            $value = $request->get_param( 'Name' );
        }
        if ( is_array( $value ) ) {
            if ( ! in_array( $key, Therese_Sync_Fields::MULTILINE, true ) ) {
                return '';
            }
            $value = implode(
                "\n",
                array_map(
                    static function ( $line ) {
                        return is_scalar( $line ) ? (string) $line : '';
                    },
                    $value
                )
            );
        }
        $value = (string) $value;
        if ( in_array( $key, Therese_Sync_Fields::MULTILINE, true ) ) {
            $value = str_replace( array( "\r\n", "\r" ), "\n", $value );
            return trim( sanitize_textarea_field( $value ) );
        }
        return trim( sanitize_text_field( $value ) );
    }

    private static function handle_picture( WP_REST_Request $request, int $post_id ) {
        $files = $request->get_file_params();
        if ( empty( $files['picture'] ) || empty( $files['picture']['tmp_name'] ) ) {
            return null;
        }
        require_once ABSPATH . 'wp-admin/includes/file.php';
        require_once ABSPATH . 'wp-admin/includes/media.php';
        require_once ABSPATH . 'wp-admin/includes/image.php';
        $attachment_id = media_handle_upload( 'picture', $post_id );
        if ( is_wp_error( $attachment_id ) ) {
            $attachment_id->add_data( array( 'status' => 400 ) );
            return $attachment_id;
        }
        return (int) $attachment_id;
    }

    private static function fail( string $code, string $message, int $status ) {
        return new WP_Error( $code, $message, array( 'status' => $status ) );
    }
}
