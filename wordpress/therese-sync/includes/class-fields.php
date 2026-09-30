<?php

defined( 'ABSPATH' ) || exit;

final class Therese_Sync_Fields {
    public const PARAMS = array(
        'name',
        'linkmember',
        'position',
        'phone',
        'mobile',
        'email',
        'address',
        'websideadressfield',
        'linkfieldaddress',
        'picture',
    );

    public const MULTILINE = array( 'address' );

    public static function post_types(): array {
        $types = get_post_types( array( 'show_ui' => true ), 'objects' );
        unset( $types['attachment'], $types['wp_block'], $types['wp_navigation'] );
        $out = array();
        foreach ( $types as $name => $object ) {
            $out[ $name ] = $object->labels->singular_name . ' (' . $name . ')';
        }
        return $out;
    }

    public static function targets( string $post_type, bool $for_picture ): array {
        $options = array( '' => __( '— nicht zugeordnet —', 'therese-sync' ) );
        if ( $for_picture ) {
            $options['featured_image'] = __( 'Beitragsbild', 'therese-sync' );
        } else {
            $options['post_content'] = __( 'Inhalt', 'therese-sync' );
            $options['post_excerpt'] = __( 'Textauszug', 'therese-sync' );
        }
        foreach ( self::acf_fields( $post_type, $for_picture ) as $name => $label ) {
            $options[ 'acf:' . $name ] = 'ACF: ' . $label;
        }
        foreach ( self::meta_keys( $post_type ) as $key ) {
            $options[ 'meta:' . $key ] = 'Meta: ' . $key;
        }
        return $options;
    }

    public static function acf_fields( string $post_type, bool $for_picture ): array {
        if ( ! function_exists( 'acf_get_field_groups' ) || ! function_exists( 'acf_get_fields' ) ) {
            return array();
        }
        $groups = acf_get_field_groups();
        if ( ! is_array( $groups ) ) {
            return array();
        }
        $matched = array();
        $all     = array();
        foreach ( $groups as $group ) {
            $fields = self::acf_group_fields( $group );
            $group_title = (string) ( $group['title'] ?? '' );
            $collected = self::collect_acf_fields( $fields, $for_picture, $group_title );
            foreach ( $collected as $name => $label ) {
                $all[ $name ] = $label;
            }
            if ( $post_type === '' || self::acf_group_targets_post_type( $group, $post_type ) ) {
                foreach ( $collected as $name => $label ) {
                    $matched[ $name ] = $label;
                }
            }
        }
        return $matched ?: $all;
    }

    public static function meta_keys( string $post_type ): array {
        global $wpdb;
        $keys = array();
        if ( $post_type ) {
            $found = $wpdb->get_col(
                $wpdb->prepare(
                    "SELECT DISTINCT pm.meta_key
                     FROM {$wpdb->postmeta} pm
                     INNER JOIN {$wpdb->posts} p ON p.ID = pm.post_id
                     WHERE p.post_type = %s
                       AND LEFT(pm.meta_key, 1) <> '_'
                     ORDER BY pm.meta_key ASC
                     LIMIT 200",
                    $post_type
                )
            );
            foreach ( $found ?: array() as $key ) {
                $keys[] = (string) $key;
            }
            if ( function_exists( 'get_registered_meta_keys' ) ) {
                foreach ( array( $post_type, '' ) as $subtype ) {
                    foreach ( array_keys( (array) get_registered_meta_keys( 'post', $subtype ) ) as $key ) {
                        $key = (string) $key;
                        if ( $key !== '' && ! str_starts_with( $key, '_' ) ) {
                            $keys[] = $key;
                        }
                    }
                }
            }
        }
        $keys = array_values( array_unique( array_filter( $keys ) ) );
        natcasesort( $keys );
        return array_values( $keys );
    }

    public static function parse_target( string $raw, string $custom_meta ): string {
        $custom_meta = preg_replace( '/[^A-Za-z0-9_\-]/', '', str_replace( ' ', '_', $custom_meta ) ) ?? '';
        if ( $custom_meta !== '' ) {
            return 'meta:' . $custom_meta;
        }
        $raw = trim( $raw );
        if ( $raw === '' ) {
            return '';
        }
        if ( in_array( $raw, array( 'post_content', 'post_excerpt', 'featured_image' ), true ) ) {
            return $raw;
        }
        if ( str_starts_with( $raw, 'acf:' ) || str_starts_with( $raw, 'meta:' ) ) {
            return $raw;
        }
        return '';
    }

    public static function find_by_posttitle( string $post_type, string $posttitle ): array {
        global $wpdb;
        $posttitle = trim( $posttitle );
        if ( $post_type === '' || $posttitle === '' ) {
            return array();
        }
        $ids = $wpdb->get_col(
            $wpdb->prepare(
                "SELECT ID FROM {$wpdb->posts}
                 WHERE post_type = %s AND post_title = %s AND post_status != 'trash'
                 ORDER BY ID ASC",
                $post_type,
                $posttitle
            )
        );
        return array_map( 'intval', $ids ?: array() );
    }

    public static function find_by_name( string $post_type, string $map_target, string $name ): array {
        global $wpdb;
        $name = trim( $name );
        if ( $post_type === '' || $map_target === '' || $name === '' ) {
            return array();
        }
        if ( in_array( $map_target, array( 'post_content', 'post_excerpt' ), true ) ) {
            $column = $map_target === 'post_content' ? 'post_content' : 'post_excerpt';
            $ids = $wpdb->get_col(
                $wpdb->prepare(
                    "SELECT ID FROM {$wpdb->posts}
                     WHERE post_type = %s AND {$column} = %s AND post_status != 'trash'
                     ORDER BY ID ASC",
                    $post_type,
                    $name
                )
            );
            return array_map( 'intval', $ids ?: array() );
        }
        $meta_key = self::meta_key_for_target( $map_target );
        if ( $meta_key === '' ) {
            return array();
        }
        $ids = $wpdb->get_col(
            $wpdb->prepare(
                "SELECT p.ID FROM {$wpdb->posts} p
                 INNER JOIN {$wpdb->postmeta} pm ON pm.post_id = p.ID
                 WHERE p.post_type = %s AND p.post_status != 'trash'
                   AND pm.meta_key = %s AND pm.meta_value = %s
                 ORDER BY p.ID ASC",
                $post_type,
                $meta_key,
                $name
            )
        );
        return array_map( 'intval', $ids ?: array() );
    }

    public static function meta_key_for_target( string $target ): string {
        if ( str_starts_with( $target, 'meta:' ) ) {
            return substr( $target, 5 );
        }
        if ( str_starts_with( $target, 'acf:' ) ) {
            return substr( $target, 4 );
        }
        return '';
    }

    public static function apply( int $post_id, array $map, array $values, $picture_id = null ): void {
        $post_update = array();
        foreach ( self::PARAMS as $param ) {
            if ( $param === 'picture' ) {
                continue;
            }
            if ( ! array_key_exists( $param, $values ) ) {
                continue;
            }
            $target = (string) ( $map[ $param ] ?? '' );
            if ( $target === '' ) {
                continue;
            }
            $value = is_string( $values[ $param ] ) ? $values[ $param ] : (string) $values[ $param ];
            self::write_value( $post_id, $target, $value, $post_update );
        }
        if ( $picture_id && ! empty( $map['picture'] ) ) {
            self::write_picture( $post_id, (string) $map['picture'], (int) $picture_id );
        }
        if ( $post_update ) {
            $post_update['ID'] = $post_id;
            wp_update_post( $post_update );
        }
    }

    public static function read( int $post_id, array $map ): array {
        $out = array();
        foreach ( self::PARAMS as $param ) {
            $target = (string) ( $map[ $param ] ?? '' );
            if ( $target === '' ) {
                $out[ $param ] = null;
                continue;
            }
            if ( $param === 'picture' ) {
                $out[ $param ] = self::read_picture( $post_id, $target );
                continue;
            }
            $out[ $param ] = self::read_value( $post_id, $target );
        }
        return $out;
    }

    private static function acf_group_targets_post_type( array $group, string $post_type ): bool {
        $locations = $group['location'] ?? null;
        if ( ! is_array( $locations ) || $locations === array() ) {
            return true;
        }
        foreach ( $locations as $rules ) {
            $ok = true;
            $has_post_type_rule = false;
            foreach ( (array) $rules as $rule ) {
                if ( ( $rule['param'] ?? '' ) !== 'post_type' ) {
                    continue;
                }
                $has_post_type_rule = true;
                $value    = (string) ( $rule['value'] ?? '' );
                $operator = (string) ( $rule['operator'] ?? '==' );
                $match    = $operator === '!=' ? $value !== $post_type : $value === $post_type;
                if ( ! $match ) {
                    $ok = false;
                    break;
                }
            }
            if ( $ok && $has_post_type_rule ) {
                return true;
            }
        }
        return false;
    }

    private static function acf_group_fields( array $group ): array {
        $fields = false;
        if ( ! empty( $group['key'] ) ) {
            $fields = acf_get_fields( $group['key'] );
        }
        if ( ! $fields && ! empty( $group['ID'] ) ) {
            $fields = acf_get_fields( $group['ID'] );
        }
        if ( ! $fields ) {
            $fields = acf_get_fields( $group );
        }
        return is_array( $fields ) ? $fields : array();
    }

    private static function collect_acf_fields( array $fields, bool $for_picture, string $label_prefix = '' ): array {
        $out = array();
        foreach ( $fields as $field ) {
            if ( ! is_array( $field ) ) {
                continue;
            }
            $name  = (string) ( $field['name'] ?? '' );
            $type  = (string) ( $field['type'] ?? '' );
            $label = (string) ( $field['label'] ?? $name );
            if ( $label_prefix !== '' ) {
                $label = $label_prefix . ' → ' . $label;
            }
            if ( ! empty( $field['sub_fields'] ) && is_array( $field['sub_fields'] ) ) {
                $out = array_merge( $out, self::collect_acf_fields( $field['sub_fields'], $for_picture, $label ) );
                continue;
            }
            if ( $name === '' || in_array( $type, array( 'tab', 'accordion', 'message', 'repeater', 'flexible_content' ), true ) ) {
                continue;
            }
            $is_image = in_array( $type, array( 'image', 'file' ), true );
            if ( $for_picture !== $is_image ) {
                continue;
            }
            $out[ $name ] = $label;
        }
        return $out;
    }

    private static function write_value( int $post_id, string $target, string $value, array &$post_update ): void {
        if ( $target === 'post_content' ) {
            $post_update['post_content'] = $value;
            return;
        }
        if ( $target === 'post_excerpt' ) {
            $post_update['post_excerpt'] = $value;
            return;
        }
        if ( str_starts_with( $target, 'acf:' ) && function_exists( 'update_field' ) ) {
            update_field( substr( $target, 4 ), $value, $post_id );
            return;
        }
        $meta_key = self::meta_key_for_target( $target );
        if ( $meta_key !== '' ) {
            update_post_meta( $post_id, $meta_key, $value );
        }
    }

    private static function write_picture( int $post_id, string $target, int $attachment_id ): void {
        if ( $target === 'featured_image' ) {
            set_post_thumbnail( $post_id, $attachment_id );
            return;
        }
        if ( str_starts_with( $target, 'acf:' ) && function_exists( 'update_field' ) ) {
            update_field( substr( $target, 4 ), $attachment_id, $post_id );
            return;
        }
        $meta_key = self::meta_key_for_target( $target );
        if ( $meta_key !== '' ) {
            update_post_meta( $post_id, $meta_key, $attachment_id );
        }
    }

    private static function read_value( int $post_id, string $target ): ?string {
        $post = get_post( $post_id );
        if ( ! $post ) {
            return null;
        }
        if ( $target === 'post_content' ) {
            return (string) $post->post_content;
        }
        if ( $target === 'post_excerpt' ) {
            return (string) $post->post_excerpt;
        }
        if ( str_starts_with( $target, 'acf:' ) && function_exists( 'get_field' ) ) {
            $value = get_field( substr( $target, 4 ), $post_id );
            return self::stringify( $value );
        }
        $meta_key = self::meta_key_for_target( $target );
        if ( $meta_key !== '' ) {
            $value = get_post_meta( $post_id, $meta_key, true );
            return self::stringify( $value );
        }
        return null;
    }

    private static function read_picture( int $post_id, string $target ): ?string {
        $attachment_id = 0;
        if ( $target === 'featured_image' ) {
            $attachment_id = (int) get_post_thumbnail_id( $post_id );
        } elseif ( str_starts_with( $target, 'acf:' ) && function_exists( 'get_field' ) ) {
            $value = get_field( substr( $target, 4 ), $post_id );
            if ( is_array( $value ) ) {
                $attachment_id = (int) ( $value['ID'] ?? $value['id'] ?? 0 );
            } else {
                $attachment_id = (int) $value;
            }
        } else {
            $meta_key = self::meta_key_for_target( $target );
            if ( $meta_key !== '' ) {
                $attachment_id = (int) get_post_meta( $post_id, $meta_key, true );
            }
        }
        if ( $attachment_id <= 0 ) {
            return null;
        }
        $url = wp_get_attachment_url( $attachment_id );
        return $url ? (string) $url : null;
    }

    private static function stringify( $value ): ?string {
        if ( $value === null || $value === false ) {
            return null;
        }
        if ( is_array( $value ) ) {
            if ( isset( $value['url'] ) ) {
                return (string) $value['url'];
            }
            return wp_json_encode( $value ) ?: null;
        }
        return (string) $value;
    }
}
