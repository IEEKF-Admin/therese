<?php

defined( 'ABSPATH' ) || exit;

final class Therese_Sync_Settings {
    public const OPTION = 'therese_sync';

    public static function defaults(): array {
        $map = array();
        foreach ( Therese_Sync_Fields::PARAMS as $param ) {
            $map[ $param ] = '';
        }
        return array(
            'post_type'  => '',
            'map'        => $map,
            'whitelist'  => array(),
        );
    }

    public static function get(): array {
        $saved = get_option( self::OPTION, array() );
        if ( ! is_array( $saved ) ) {
            $saved = array();
        }
        $data = array_merge( self::defaults(), $saved );
        $data['post_type'] = sanitize_key( (string) $data['post_type'] );
        $data['whitelist'] = array_values( array_unique( array_map( 'intval', (array) $data['whitelist'] ) ) );
        $map = self::defaults()['map'];
        foreach ( Therese_Sync_Fields::PARAMS as $param ) {
            $map[ $param ] = sanitize_text_field( (string) ( $saved['map'][ $param ] ?? '' ) );
        }
        $data['map'] = $map;
        return $data;
    }

    public static function user_is_allowed( int $user_id ): bool {
        if ( $user_id <= 0 ) {
            return false;
        }
        return in_array( $user_id, self::get()['whitelist'], true );
    }

    public static function register_menu(): void {
        add_options_page(
            'THERESE Sync',
            'THERESE Sync',
            'manage_options',
            'therese-sync',
            array( self::class, 'render' )
        );
    }

    public static function register(): void {
        register_setting(
            'therese_sync',
            self::OPTION,
            array(
                'type'              => 'array',
                'sanitize_callback' => array( self::class, 'sanitize' ),
                'default'           => self::defaults(),
            )
        );
    }

    public static function sanitize( $input ): array {
        $current = self::get();
        $input = is_array( $input ) ? $input : array();
        $post_type = sanitize_key( (string) ( $input['post_type'] ?? '' ) );
        $types = Therese_Sync_Fields::post_types();
        if ( $post_type !== '' && ! isset( $types[ $post_type ] ) ) {
            $post_type = $current['post_type'];
        }
        $map = self::defaults()['map'];
        foreach ( Therese_Sync_Fields::PARAMS as $param ) {
            $raw = (string) ( $input['map'][ $param ] ?? '' );
            $custom = (string) ( $input['map_meta'][ $param ] ?? '' );
            $map[ $param ] = Therese_Sync_Fields::parse_target( $raw, $custom );
        }
        $whitelist = array();
        foreach ( (array) ( $input['whitelist'] ?? array() ) as $user_id ) {
            $user_id = (int) $user_id;
            if ( $user_id > 0 && get_userdata( $user_id ) ) {
                $whitelist[] = $user_id;
            }
        }
        return array(
            'post_type' => $post_type,
            'map'       => $map,
            'whitelist' => array_values( array_unique( $whitelist ) ),
        );
    }

    public static function render(): void {
        if ( ! current_user_can( 'manage_options' ) ) {
            return;
        }
        $data = self::get();
        $types = Therese_Sync_Fields::post_types();
        $users = get_users( array( 'orderby' => 'display_name' ) );
        $rest  = esc_url_raw( rest_url( 'therese/v1/' ) );
        echo '<div class="wrap">';
        echo '<h1>THERESE Sync</h1>';
        echo '<p>' . esc_html__( 'REST-API für THERESE. Ein Post-Typ pro Website. Authentifizierung nur per Application Password über HTTPS.', 'therese-sync' ) . '</p>';
        echo '<p><code>' . esc_html( $rest ) . '</code></p>';
        if ( function_exists( 'wp_is_application_passwords_available' ) && ! wp_is_application_passwords_available() ) {
            echo '<div class="notice notice-warning"><p>';
            echo esc_html__( 'Application Passwords sind auf dieser Website nicht verfügbar. In der Regel ist HTTPS nötig.', 'therese-sync' );
            echo '</p></div>';
        }
        echo '<form method="post" action="options.php">';
        settings_fields( 'therese_sync' );
        echo '<table class="form-table" role="presentation">';
        echo '<tr><th scope="row"><label for="therese_sync_post_type">' . esc_html__( 'Post-Typ', 'therese-sync' ) . '</label></th><td>';
        echo '<select name="' . esc_attr( self::OPTION ) . '[post_type]" id="therese_sync_post_type">';
        echo '<option value="">' . esc_html__( '— wählen —', 'therese-sync' ) . '</option>';
        foreach ( $types as $name => $label ) {
            echo '<option value="' . esc_attr( $name ) . '" ' . selected( $data['post_type'], $name, false ) . '>' . esc_html( $label ) . '</option>';
        }
        echo '</select>';
        echo '<p class="description">' . esc_html__( 'Beim Wechsel des Post-Typs wird die Feldliste neu geladen.', 'therese-sync' ) . '</p>';
        echo '</td></tr></table>';

        echo '<h2>' . esc_html__( 'Feldzuordnung', 'therese-sync' ) . '</h2>';
        echo '<p class="description">' . esc_html__( 'posttitle wird immer als WordPress-Titel gesetzt und ist der eindeutige Schlüssel. Name ist nur Vor- und Nachname. address ist mehrzeilig — auf Textarea, Inhalt oder ein entsprechendes ACF-Feld legen.', 'therese-sync' ) . '</p>';
        if ( ! function_exists( 'acf_get_field_groups' ) ) {
            echo '<p class="description">' . esc_html__( 'ACF ist nicht aktiv. Native Post-Felder und vorhandene Meta-Keys stehen trotzdem zur Verfügung.', 'therese-sync' ) . '</p>';
        }
        echo '<table class="widefat striped">';
        echo '<thead><tr><th>' . esc_html__( 'API-Parameter', 'therese-sync' ) . '</th><th>' . esc_html__( 'Feld', 'therese-sync' ) . '</th><th>' . esc_html__( 'Oder Meta-Key', 'therese-sync' ) . '</th></tr></thead><tbody>';
        foreach ( Therese_Sync_Fields::PARAMS as $param ) {
            $for_picture = $param === 'picture';
            $targets = Therese_Sync_Fields::targets( $data['post_type'], $for_picture );
            $current = (string) ( $data['map'][ $param ] ?? '' );
            if ( $current !== '' && ! isset( $targets[ $current ] ) ) {
                $targets[ $current ] = $current;
            }
            echo '<tr>';
            echo '<th scope="row"><code>' . esc_html( $param ) . '</code>';
            if ( in_array( $param, Therese_Sync_Fields::MULTILINE, true ) ) {
                echo '<br><span class="description">' . esc_html__( 'mehrzeilig', 'therese-sync' ) . '</span>';
            }
            echo '</th>';
            echo '<td><select name="' . esc_attr( self::OPTION ) . '[map][' . esc_attr( $param ) . ']">';
            foreach ( $targets as $value => $label ) {
                echo '<option value="' . esc_attr( $value ) . '" ' . selected( $current, $value, false ) . '>' . esc_html( $label ) . '</option>';
            }
            echo '</select></td>';
            echo '<td><input type="text" class="regular-text" name="' . esc_attr( self::OPTION ) . '[map_meta][' . esc_attr( $param ) . ']" value="" placeholder="staff_phone" autocomplete="off"></td>';
            echo '</tr>';
        }
        echo '</tbody></table>';

        echo '<h2>' . esc_html__( 'API-Benutzer (Whitelist)', 'therese-sync' ) . '</h2>';
        echo '<p class="description">' . esc_html__( 'Nur diese WordPress-Benutzer dürfen die Schnittstelle mit ihrem Application Password nutzen. Unter Benutzer → Profil ein Anwendungspasswort erzeugen.', 'therese-sync' ) . '</p>';
        echo '<table class="widefat striped"><tbody>';
        foreach ( $users as $user ) {
            $checked = in_array( (int) $user->ID, $data['whitelist'], true );
            echo '<tr><td style="width:2rem;">';
            echo '<input type="checkbox" name="' . esc_attr( self::OPTION ) . '[whitelist][]" value="' . esc_attr( (string) $user->ID ) . '" ' . checked( $checked, true, false ) . '>';
            echo '</td><td>' . esc_html( $user->display_name ) . ' <code>' . esc_html( $user->user_login ) . '</code></td></tr>';
        }
        echo '</tbody></table>';
        submit_button();
        echo '</form>';
        self::render_mapping_script();
        echo '</div>';
    }

    public static function ajax_targets(): void {
        if ( ! current_user_can( 'manage_options' ) ) {
            wp_send_json_error( null, 403 );
        }
        check_ajax_referer( 'therese_sync_targets', 'nonce' );
        $post_type = sanitize_key( wp_unslash( (string) ( $_POST['post_type'] ?? '' ) ) );
        $types = Therese_Sync_Fields::post_types();
        if ( $post_type !== '' && ! isset( $types[ $post_type ] ) ) {
            $post_type = '';
        }
        wp_send_json_success( array(
            'text'    => self::select_options( Therese_Sync_Fields::targets( $post_type, false ) ),
            'picture' => self::select_options( Therese_Sync_Fields::targets( $post_type, true ) ),
        ) );
    }

    private static function select_options( array $targets ): array {
        $out = array();
        foreach ( $targets as $value => $label ) {
            $out[] = array(
                'value' => (string) $value,
                'label' => (string) $label,
            );
        }
        return $out;
    }

    private static function render_mapping_script(): void {
        $nonce = wp_create_nonce( 'therese_sync_targets' );
        $ajax  = admin_url( 'admin-ajax.php' );
        echo '<script>';
        echo '(function(){';
        echo 'var sel=document.getElementById("therese_sync_post_type");';
        echo 'if(!sel)return;';
        echo 'var ajaxurl=' . wp_json_encode( $ajax ) . ';';
        echo 'var nonce=' . wp_json_encode( $nonce ) . ';';
        echo 'function fill(select,items){var current=select.value;select.innerHTML="";var found=false;';
        echo '(items||[]).forEach(function(item){var opt=document.createElement("option");opt.value=item.value;opt.textContent=item.label;if(item.value===current){opt.selected=true;found=true;}select.appendChild(opt);});';
        echo 'if(current&&!found){var opt=document.createElement("option");opt.value=current;opt.textContent=current;opt.selected=true;select.appendChild(opt);}}';
        echo 'function refresh(){var body=new FormData();body.append("action","therese_sync_targets");body.append("nonce",nonce);body.append("post_type",sel.value);';
        echo 'fetch(ajaxurl,{method:"POST",body:body,credentials:"same-origin"}).then(function(r){return r.json();}).then(function(res){';
        echo 'if(!res||!res.success)return;';
        echo 'document.querySelectorAll(\'select[name^="therese_sync[map]"]\').forEach(function(mapSel){';
        echo 'var picture=mapSel.name==="therese_sync[map][picture]";';
        echo 'fill(mapSel,picture?res.data.picture:res.data.text);';
        echo '});});}';
        echo 'sel.addEventListener("change",refresh);';
        echo '})();';
        echo '</script>';
    }
}
