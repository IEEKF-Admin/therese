(function() {
    function moveSelected(fromSelect, toSelect) {
        Array.prototype.slice.call(fromSelect.selectedOptions).forEach(function(opt) {
            opt.selected = false;
            toSelect.appendChild(opt);
        });
        sortOptions(toSelect);
    }

    function moveAll(fromSelect, toSelect) {
        Array.prototype.slice.call(fromSelect.options).forEach(function(opt) {
            opt.selected = false;
            toSelect.appendChild(opt);
        });
        sortOptions(toSelect);
    }

    function sortOptions(select) {
        var opts = Array.prototype.slice.call(select.options);
        opts.sort(function(a, b) {
            return a.textContent.localeCompare(b.textContent, undefined, { sensitivity: 'base' });
        });
        opts.forEach(function(opt) { select.appendChild(opt); });
    }

    function initDualList(root) {
        if (root.dataset.dualListReady === '1') return;
        root.dataset.dualListReady = '1';

        var available = root.querySelector('.dual-list-available');
        var selected = root.querySelector('.dual-list-selected')
            || root.querySelector('.dual-list-panel:last-child select');
        if (!available || !selected) return;

        var fieldName = selected.getAttribute('name');
        if (fieldName) {
            selected.removeAttribute('name');
            selected.removeAttribute('required');
        }
        var holder = root.querySelector('[data-dual-list-values]');
        if (!holder) {
            holder = document.createElement('div');
            holder.setAttribute('data-dual-list-values', fieldName || '');
            holder.hidden = true;
            root.appendChild(holder);
        }

        function syncHidden() {
            holder.innerHTML = '';
            if (!fieldName) return;
            Array.prototype.forEach.call(selected.options, function(opt) {
                var input = document.createElement('input');
                input.type = 'hidden';
                input.name = fieldName;
                input.value = opt.value;
                holder.appendChild(input);
            });
        }

        var addBtn = root.querySelector('.dual-list-add');
        var removeBtn = root.querySelector('.dual-list-remove');
        var addAllBtn = root.querySelector('.dual-list-add-all');
        var removeAllBtn = root.querySelector('.dual-list-remove-all');

        if (addBtn) addBtn.addEventListener('click', function() { moveSelected(available, selected); syncHidden(); });
        if (removeBtn) removeBtn.addEventListener('click', function() { moveSelected(selected, available); syncHidden(); });
        if (addAllBtn) addAllBtn.addEventListener('click', function() { moveAll(available, selected); syncHidden(); });
        if (removeAllBtn) removeAllBtn.addEventListener('click', function() { moveAll(selected, available); syncHidden(); });

        available.addEventListener('dblclick', function() { moveSelected(available, selected); syncHidden(); });
        selected.addEventListener('dblclick', function() { moveSelected(selected, available); syncHidden(); });
        syncHidden();
    }

    function setDualListValues(selectedSelect, values) {
        var selected = typeof selectedSelect === 'string'
            ? document.getElementById(selectedSelect)
            : selectedSelect;
        if (!selected) return;
        var root = selected.closest('[data-dual-list]');
        if (!root) return;
        initDualList(root);
        var available = root.querySelector('.dual-list-available');
        if (!available) return;
        var valueSet = new Set((values || []).map(String));
        Array.prototype.slice.call(selected.options).forEach(function(opt) {
            available.appendChild(opt);
        });
        Array.prototype.slice.call(available.options).forEach(function(opt) {
            if (valueSet.has(String(opt.value))) {
                opt.selected = false;
                selected.appendChild(opt);
            }
        });
        sortOptions(available);
        sortOptions(selected);
        var holder = root.querySelector('[data-dual-list-values]');
        if (holder) {
            var fieldName = holder.getAttribute('data-dual-list-values');
            holder.innerHTML = '';
            if (fieldName) {
                Array.prototype.forEach.call(selected.options, function(opt) {
                    var input = document.createElement('input');
                    input.type = 'hidden';
                    input.name = fieldName;
                    input.value = opt.value;
                    holder.appendChild(input);
                });
            }
        }
    }

    function initAll() {
        document.querySelectorAll('[data-dual-list]').forEach(initDualList);
    }

    window.setDualListValues = setDualListValues;
    window.initDualListWidgets = initAll;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initAll);
    } else {
        initAll();
    }
})();
