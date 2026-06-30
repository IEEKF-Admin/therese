// therese/static/admin/js/building_room_phone_dynamic.js
(function() {
    function init() {
        if (typeof django === 'undefined' || typeof django.jQuery === 'undefined') {
            setTimeout(init, 50);
            return;
        }

        var $ = django.jQuery;
        var buildingSelect = $('#id_building');
        var roomSelect = $('#id_room');
        var phoneSelect = $('#id_phone_number');

        var allRoomOptions = roomSelect.find('option').clone();

        console.log('DEBUG: JS geladen -', allRoomOptions.length, 'RÃ¤ume gespeichert');

        buildingSelect.on('change', function() {
            var selectedText = $(this).find('option:selected').text().trim();
            var buildingNumber = selectedText.split(' - ')[0];

            console.log('\n=== BUILDING CHANGED ===', selectedText, '(Nummer:', buildingNumber, ')');

            roomSelect.empty();
            roomSelect.append($('<option>').val('').text('---------'));

            if (!buildingNumber || buildingNumber === '---------') {
                console.log('Kein Building gewÃ¤hlt â†’ alle RÃ¤ume anzeigen');
                allRoomOptions.each(function() {
                    roomSelect.append($(this).clone());
                });
                return;
            }

            var hasRooms = false;
            allRoomOptions.each(function() {
                var optionText = $(this).text().trim();

                // Neue, tolerante Suche: EnthÃ¤lt der Text die Building-Nummer am Anfang?
                if (optionText.match(new RegExp('^' + buildingNumber + '(\\s|-)'))) {
                    roomSelect.append($(this).clone());
                    hasRooms = true;
                    console.log('MATCH:', optionText);
                }
            });

            if (!hasRooms) {
                roomSelect.append($('<option>').val('').text('Keine RÃ¤ume fÃ¼r dieses GebÃ¤ude'));
                console.log('KEIN MATCH fÃ¼r Nummer', buildingNumber);
            } else {
                console.log('Erfolgreich gefiltert');
            }
        });

        roomSelect.on('change', function() {
            var selectedText = $(this).find('option:selected').text().trim();
            var phoneMatch = selectedText.match(/(\+?\d[\d\s\-\(\)]{8,})/);

            phoneSelect.empty();
            phoneSelect.append($('<option>').val('').text('---------'));

            if (phoneMatch) {
                var phone = phoneMatch[1].trim();
                phoneSelect.append($('<option>').val(phone).text(phone).prop('selected', true));
                console.log('â†’ Office Phone gesetzt:', phone);
            }
        });

        if (buildingSelect.val()) {
            buildingSelect.trigger('change');
        }
    }

    init();
})();

