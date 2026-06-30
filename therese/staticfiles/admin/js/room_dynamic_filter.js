// therese/static/admin/js/room_dynamic_filter.js
django.jQuery(function($) {
    function filterRooms() {
        var buildingId = $('#id_room').data('building') || $('#id_building').val(); // fallback falls nötig
        // Fürs Erste: Room wird später dynamisch gefiltert – hier Platzhalter
        // Wir können das später erweitern, wenn du möchtest
    }

    // Vorläufig: Nur sicherstellen, dass keine + Icons erscheinen
    $('select').each(function() {
        if (this.id.includes('room') || this.id.includes('building')) {
            // zusätzliche Sicherheit
        }
    });
});