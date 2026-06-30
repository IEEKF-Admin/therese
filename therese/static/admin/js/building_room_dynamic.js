// therese/static/admin/js/building_room_dynamic.js
(function() {
    function init() {
        if (typeof django === 'undefined' || typeof django.jQuery === 'undefined') {
            setTimeout(init, 50);
            return;
        }

        var $ = django.jQuery;
        var buildingSelect = $('#id_building');
        var buildingNumberField = $('#id_building_number');

        if (buildingSelect.length && buildingNumberField.length) {
            buildingSelect.on('change', function() {
                var selectedText = $(this).find('option:selected').text().trim();
                var buildingNumber = selectedText.split(' - ')[0];

                if (buildingNumber && buildingNumber !== '---------') {
                    buildingNumberField.val(buildingNumber);
                }
            });

            if (buildingSelect.val()) {
                buildingSelect.trigger('change');
            }
        }
    }

    init();
})();

