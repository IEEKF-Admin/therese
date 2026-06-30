document.addEventListener('DOMContentLoaded', function() {
    const buildingSelect = document.querySelector('.building-select');
    const roomSelect     = document.querySelector('.room-select');
    const phoneSelect    = document.querySelector('.phone-select');

    if (!buildingSelect || !roomSelect || !phoneSelect) return;

    // Building â†’ Room
    buildingSelect.addEventListener('change', function() {
        const buildingId = this.value;
        roomSelect.innerHTML = '<option value="">â€” Loading rooms... â€”</option>';
        phoneSelect.innerHTML = '<option value="">â€” Select Room first â€”</option>';

        if (!buildingId) {
            roomSelect.innerHTML = '<option value="">â€” Select Building first â€”</option>';
            return;
        }

        fetch(`/hr/ajax/rooms-by-building/?building=${buildingId}`)
            .then(r => r.json())
            .then(data => {
                roomSelect.innerHTML = '<option value="">â€” Select Room â€”</option>';
                data.forEach(room => {
                    const opt = document.createElement('option');
                    opt.value = room.id;
                    opt.textContent = room.display;
                    roomSelect.appendChild(opt);
                });
            });
    });

    // Room â†’ Phone
    roomSelect.addEventListener('change', function() {
        const roomId = this.value;
        phoneSelect.innerHTML = '<option value="">â€” Loading phones... â€”</option>';

        if (!roomId) {
            phoneSelect.innerHTML = '<option value="">â€” Select Room first â€”</option>';
            return;
        }

        fetch(`/hr/ajax/phonenumbers-by-room/?room=${roomId}`)
            .then(r => r.json())
            .then(data => {
                phoneSelect.innerHTML = '<option value="">â€” Select Phone â€”</option>';
                data.forEach(phone => {
                    const opt = document.createElement('option');
                    opt.value = phone.phone_number;
                    opt.textContent = phone.phone_number;
                    phoneSelect.appendChild(opt);
                });
            });
    });
});

