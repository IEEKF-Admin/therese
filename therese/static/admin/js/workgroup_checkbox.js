// therese/static/admin/js/workgroup_checkbox.js

document.addEventListener('DOMContentLoaded', function() {
    const checkbox = document.querySelector('input[name="create_new_workgroup"]');
    const inlineGroups = document.querySelectorAll('.inline-group');

    let workgroupInline = null;
    inlineGroups.forEach(group => {
        const heading = group.querySelector('h2');
        if (heading && heading.textContent.includes('New Workgroup')) {
            workgroupInline = group;
        }
    });

    if (!checkbox || !workgroupInline) return;

    function toggleInline() {
        workgroupInline.style.display = checkbox.checked ? 'table' : 'none';
    }

    checkbox.addEventListener('change', toggleInline);
    toggleInline(); // initial state
});