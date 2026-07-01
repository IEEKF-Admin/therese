// therese/static/admin/js/room_dynamic_filter.js
django.jQuery(function($) {
    function filterRooms() {
        var buildingId = $('#id_room').data('building') || $('#id_building').val(); // fallback falls nÃ¶tig
        // FÃ¼rs Erste: Room wird spÃ¤ter dynamisch gefiltert â€“ hier Platzhalter
        // Wir kÃ¶nnen das spÃ¤ter erweitern, wenn du mÃ¶chtest
    }

    // VorlÃ¤ufig: Nur sicherstellen, dass keine + Icons erscheinen
    $('select').each(function() {
        if (this.id.includes('room') || this.id.includes('building')) {
            // zusÃ¤tzliche Sicherheit
        }
    });
});

