// therese/static/admin/js/room_phone_dynamic.js
django.jQuery(function($) {
    $('#id_room').on('change', function() {
        var selectedText = $(this).find('option:selected').text();
        var phoneMatch = selectedText.match(/(\+?\d[\d\s\-\(\)]{8,})/);
        
        var phoneSelect = $('#id_phone_number');
        phoneSelect.empty();
        phoneSelect.append($('<option>').val('').text('---------'));

        if (phoneMatch) {
            var phone = phoneMatch[1].trim();
            phoneSelect.append($('<option>').val(phone).text(phone).prop('selected', true));
        }
    });

    // Initial ausfÃ¼hren, falls bereits ein Room ausgewÃ¤hlt ist
    if ($('#id_room').val()) {
        $('#id_room').trigger('change');
    }
});

