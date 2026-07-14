// therese/static/admin/js/room_dynamic_filter.js
django.jQuery(function($) {
    function filterRooms() {
        var buildingId = $('#id_room').data('building') || $('#id_building').val(); // fallback if needed
        // For now: room will be filtered dynamically later - placeholder
        // Can be extended later if needed
    }

    // For now: ensure no + icons appear
    $('select').each(function() {
        if (this.id.includes('room') || this.id.includes('building')) {
            // additional safeguard
        }
    });
});

