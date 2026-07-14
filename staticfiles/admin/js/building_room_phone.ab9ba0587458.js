// therese/static/admin/js/building_room_phone.js
document.addEventListener('DOMContentLoaded', function() {
    console.log('=== Building-Room-Phone JS loaded ===');

    const buildingField = document.getElementById('id_building');
    const roomField = document.getElementById('id_room');
    const phoneField = document.getElementById('id_phone_number');

    console.log('Fields found:', {
        building: !!buildingField,
        room: !!roomField,
        phone: !!phoneField
    });

    if (!buildingField || !roomField || !phoneField) {
        console.error('One or more fields are missing!');
        return;
    }

    // Building Change
    buildingField.addEventListener('change', function() {
        const buildingId = this.value;
        console.log('Building changed -> ID:', buildingId);

        roomField.innerHTML = '<option value="">---------</option>';
        phoneField.innerHTML = '<option value="">---------</option>';

        if (!buildingId) {
            console.log('No building ID -> abort');
            return;
        }

        console.log('Fetching rooms for building:', buildingId);
        
        fetch(`/admin/employees/room/?building=${buildingId}`)
            .then(response => {
                console.log('Rooms Response Status:', response.status);
                return response.json();
            })
            .then(data => {
                console.log('Rooms received:', data);
                data.forEach(room => {
                    const option = document.createElement('option');
                    option.value = room.id;
                    option.textContent = room.display;
                    roomField.appendChild(option);
                });
            })
            .catch(err => console.error('Fetch Rooms Error:', err));
    });

    // Room Change
    roomField.addEventListener('change', function() {
        const roomId = this.value;
        console.log('Room changed -> ID:', roomId);

        phoneField.innerHTML = '<option value="">---------</option>';

        if (!roomId) {
            console.log('No room ID -> abort');
            return;
        }

        console.log('Fetching phones for room:', roomId);

        fetch(`/admin/employees/phonenumber/?room=${roomId}`)
            .then(response => {
                console.log('Phones Response Status:', response.status);
                return response.json();
            })
            .then(data => {
                console.log('Phone numbers received:', data);
                data.forEach(phone => {
                    const option = document.createElement('option');
                    option.value = phone.phone_number;
                    option.textContent = phone.phone_number;
                    phoneField.appendChild(option);
                });
                if (data.length > 0) {
                    phoneField.value = data[0].phone_number;
                    console.log('First phone number auto-selected');
                }
            })
            .catch(err => console.error('Fetch Phones Error:', err));
    });

    console.log('Event listeners registered successfully');
});

