// therese/static/admin/js/contract_payscale.js - Stable Final Version

document.addEventListener('DOMContentLoaded', function() {
    console.log('%câœ… contract_payscale.js v2 loaded', 'color: lime; font-weight: bold');

    function loadLevels(groupSelect) {
        const row = groupSelect.closest('tr') || groupSelect.closest('.dynamic-contract');
        if (!row) return;

        const levelSelect = row.querySelector('.experience-level');
        if (!levelSelect) return;

        const group = groupSelect.value.trim();
        levelSelect.innerHTML = '<option value="">---------</option>';

        if (!group) return;

        fetch(`/admin/finances/payscale/?group=${encodeURIComponent(group)}`)
            .then(r => r.json())
            .then(data => {
                console.log(`Loaded ${data.length} levels for ${group}`);
                data.forEach(item => {
                    const opt = document.createElement('option');
                    opt.value = item.level;
                    opt.textContent = `${item.level} (${item.salary} â‚¬)`;
                    levelSelect.appendChild(opt);
                });
            })
            .catch(err => console.error('Fetch error:', err));
    }

    document.addEventListener('change', e => {
        if (e.target.classList.contains('pay-scale-group')) {
            loadLevels(e.target);
        }
    });

    // Initial load
    document.querySelectorAll('.pay-scale-group').forEach(sel => {
        if (sel.value) loadLevels(sel);
    });
});

