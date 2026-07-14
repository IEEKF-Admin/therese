document.addEventListener('DOMContentLoaded', function() {
    const buildingSelect = document.querySelector('.building-select');
    const roomSelect     = document.querySelector('.room-select');
    const phoneSelect    = document.querySelector('.phone-select');

    if (!buildingSelect || !roomSelect || !phoneSelect) return;

    // Building -> Room
    buildingSelect.addEventListener('change', function() {
        const buildingId = this.value;
        roomSelect.innerHTML = '<option value="">— Loading rooms... —</option>';
        phoneSelect.innerHTML = '<option value="">— Select Room first —</option>';

        if (!buildingId) {
            roomSelect.innerHTML = '<option value="">— Select Building first —</option>';
            return;
        }

        fetch(`/hr/ajax/rooms-by-building/?building=${buildingId}`)
            .then(r => r.json())
            .then(data => {
                roomSelect.innerHTML = '<option value="">— Select Room —</option>';
                data.forEach(room => {
                    const opt = document.createElement('option');
                    opt.value = room.id;
                    opt.textContent = room.display;
                    roomSelect.appendChild(opt);
                });
            });
    });

    // Room -> Phone
    roomSelect.addEventListener('change', function() {
        const roomId = this.value;
        phoneSelect.innerHTML = '<option value="">— Loading phones... —</option>';

        if (!roomId) {
            phoneSelect.innerHTML = '<option value="">— Select Room first —</option>';
            return;
        }

        fetch(`/hr/ajax/phonenumbers-by-room/?room=${roomId}`)
            .then(r => r.json())
            .then(data => {
                phoneSelect.innerHTML = '<option value="">— Select Phone —</option>';
                data.forEach(phone => {
                    const opt = document.createElement('option');
                    opt.value = phone.phone_number;
                    opt.textContent = phone.phone_number;
                    phoneSelect.appendChild(opt);
                });
            });
    });
});

