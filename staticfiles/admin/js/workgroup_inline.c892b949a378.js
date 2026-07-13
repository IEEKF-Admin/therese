// therese/static/admin/js/workgroup_inline.js

document.addEventListener('DOMContentLoaded', function() {
    console.log('[DEBUG] workgroup_inline.js loaded');

    const workgroupSelect = document.querySelector('select[name="workgroup"]');
    let workgroupInline = null;

    // Find the New Workgroup inline
    document.querySelectorAll('.inline-group').forEach(group => {
        const heading = group.querySelector('h2');
        if (heading && heading.textContent.includes('New Workgroup')) {
            workgroupInline = group;
            console.log('[DEBUG] Found WorkGroupInline');
        }
    });

    if (!workgroupSelect || !workgroupInline) {
        console.log('[DEBUG] Could not find workgroup select or inline');
        return;
    }

    function toggleInline() {
        const value = workgroupSelect.value;
        console.log(`[DEBUG] workgroup changed to: ${value}`);
        if (value === '__new__') {
            workgroupInline.style.display = 'table';
            console.log('[DEBUG] Showing NEW PI inline');
        } else {
            workgroupInline.style.display = 'none';
            console.log('[DEBUG] Hiding NEW PI inline');
        }
    }

    // Initial state
    toggleInline();

    // Listen for changes
    workgroupSelect.addEventListener('change', toggleInline);
});

