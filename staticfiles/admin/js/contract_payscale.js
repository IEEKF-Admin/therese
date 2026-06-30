// static/admin/js/contract_payscale.js
console.log("=== contract_payscale.js LOADED (with salary auto-fill) ===");

document.addEventListener('DOMContentLoaded', function() {
    console.log("✅ DOM loaded - PayScale + Salary auto-fill active");

    function loadExperienceLevels(payScaleSelect) {
        const group = payScaleSelect.value;
        const row = payScaleSelect.closest('tr');
        const levelSelect = row ? row.querySelector('.experience-level') : null;

        if (!levelSelect || !group) return;

        fetch(`/admin/finances/payscale-levels/?group=${encodeURIComponent(group)}`)
            .then(r => r.json())
            .then(data => {
                levelSelect.innerHTML = '<option value="">---------</option>';
                data.forEach(item => {
                    const opt = document.createElement('option');
                    opt.value = item.level;
                    opt.textContent = `Level ${item.level} — ${item.salary} €`;
                    levelSelect.appendChild(opt);
                });
            });
    }

    function updateEmployeeSalary(levelSelect) {
        const level = levelSelect.value;
        const groupSelect = levelSelect.closest('tr').querySelector('.pay-scale-group');
        const group = groupSelect ? groupSelect.value : null;

        if (!group || !level) return;

        console.log(`[SALARY] Looking up salary for ${group} Level ${level}`);

        fetch(`/admin/finances/payscale-levels/?group=${encodeURIComponent(group)}`)
            .then(r => r.json())
            .then(data => {
                const match = data.find(item => String(item.level) === String(level));
                if (match) {
                    // Finde das Monthly Salary Feld im Hauptformular
                    const salaryInput = document.querySelector('input[name="monthly_salary"]');
                    if (salaryInput) {
                        salaryInput.value = match.salary;
                        console.log(`[SALARY] ✅ Filled Monthly Salary with ${match.salary} €`);
                    } else {
                        console.warn("[SALARY] Could not find monthly_salary input");
                    }
                }
            })
            .catch(err => console.error("[SALARY] Error:", err));
    }

    // === Event Listeners ===
    function attachListeners() {
        // Pay Scale Group
        document.querySelectorAll('.pay-scale-group').forEach(select => {
            if (!select.dataset.listenerAttached) {
                select.addEventListener('change', () => loadExperienceLevels(select));
                select.dataset.listenerAttached = 'true';
            }
        });

        // Experience Level → Salary
        document.querySelectorAll('.experience-level').forEach(select => {
            if (!select.dataset.salaryListener) {
                select.addEventListener('change', () => updateEmployeeSalary(select));
                select.dataset.salaryListener = 'true';
            }
        });
    }

    attachListeners();

    // Support for "Add another" inline rows
    document.addEventListener('formset:added', () => {
        console.log("[SALARY] New inline row added");
        setTimeout(attachListeners, 300);
    });
});