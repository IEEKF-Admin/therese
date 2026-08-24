(function() {
    function parseGermanDate(value) {
        if (!value) return null;
        const parts = value.trim().split('.');
        if (parts.length !== 3) return null;
        const day = parseInt(parts[0], 10);
        const month = parseInt(parts[1], 10);
        const year = parseInt(parts[2], 10);
        if (isNaN(day) || isNaN(month) || isNaN(year)) return null;
        return new Date(year, month - 1, day);
    }

    function contractDurationMonths(start, end) {
        if (!start || !end || end < start) return null;
        let months = (end.getFullYear() - start.getFullYear()) * 12 + (end.getMonth() - start.getMonth());
        if (end.getDate() >= start.getDate()) {
            months += 1;
        }
        return Math.max(months, 0);
    }

    function compareDuration(months, operator, threshold) {
        if (months === null || threshold === null || threshold === undefined || threshold === '') {
            return false;
        }
        const value = parseInt(threshold, 10);
        if (isNaN(value)) return false;
        if (operator === 'lt') return months < value;
        if (operator === 'lte') return months <= value;
        if (operator === 'gt') return months > value;
        if (operator === 'gte') return months >= value;
        if (operator === 'eq') return months === value;
        return false;
    }

    function getNamedFieldValue(fieldKey) {
        const wrapper = document.querySelector(`[data-recruitment-field="${fieldKey}"]`);
        const input = wrapper
            ? wrapper.querySelector('input:not([type="hidden"]):not([type="checkbox"]), select, textarea')
            : document.querySelector(`[name="${fieldKey}"]`);
        if (!input) return '';
        if (input.type === 'file') {
            return input.files && input.files.length ? 'file' : '';
        }
        return String(input.value || '').trim();
    }

    function evaluateVisibility(rule, months) {
        if (!rule) return true;
        if (rule.visibility_mode === 'never') return false;
        if (rule.visibility_mode === 'when_duration') {
            return compareDuration(
                months,
                rule.visibility_duration_operator,
                rule.visibility_duration_months,
            );
        }
        if (rule.visibility_mode === 'when_field_set') {
            const trigger = rule.visibility_trigger_field;
            if (!trigger) return false;
            return Boolean(getNamedFieldValue(trigger));
        }
        return true;
    }

    function evaluateRequired(rule, months, fieldKey, defaults) {
        if (!rule) {
            if (defaults && Object.prototype.hasOwnProperty.call(defaults, fieldKey)) {
                return defaults[fieldKey];
            }
            return false;
        }
        if (rule.required_mode === 'never') return false;
        if (rule.required_mode === 'when_duration') {
            if (!compareDuration(months, rule.required_duration_operator, rule.required_duration_months)) {
                return false;
            }
            return true;
        }
        if (rule.required_mode === 'always') return true;
        return false;
    }

    function getCurrentDurationMonths() {
        const startInput = document.querySelector('[data-contract-date][name="valid_from"], [name="valid_from"]');
        const endInput = document.querySelector('[data-contract-date][name="valid_until"], [name="valid_until"]');
        if (!startInput || !endInput) return null;
        const start = parseGermanDate(startInput.value);
        const end = parseGermanDate(endInput.value);
        return contractDurationMonths(start, end);
    }

    function getSelectedJobId() {
        const jobSelect = document.querySelector('[data-recruitment-job]');
        return jobSelect && jobSelect.value ? jobSelect.value : null;
    }

    function setFieldVisibility(fieldKey, visible) {
        document.querySelectorAll(`[data-recruitment-field="${fieldKey}"]`).forEach(function(wrapper) {
            wrapper.style.display = visible ? '' : 'none';
            wrapper.querySelectorAll('input, select, textarea').forEach(function(input) {
                if (!visible) {
                    input.removeAttribute('required');
                }
            });
        });
    }

    function setFieldRequired(fieldKey, required) {
        document.querySelectorAll(`[data-recruitment-field="${fieldKey}"]`).forEach(function(wrapper) {
            wrapper.querySelectorAll('input, select, textarea').forEach(function(input) {
                if (input.type === 'hidden' || input.type === 'checkbox') return;
                if (required) {
                    input.setAttribute('required', 'required');
                } else {
                    input.removeAttribute('required');
                }
            });
        });
        document.querySelectorAll(`[data-required-for="${fieldKey}"]`).forEach(function(marker) {
            marker.textContent = required ? '*' : '';
        });
        document.querySelectorAll(`label [data-required-label="${fieldKey}"]`).forEach(function(marker) {
            marker.textContent = required ? '*' : '';
        });
    }

    function applyJobFieldRules(config) {
        const jobId = getSelectedJobId();
        const months = getCurrentDurationMonths();
        const jobRules = jobId && config.jobRules[jobId] ? config.jobRules[jobId] : {};
        const defaults = config.defaultRequired || {};

        Object.keys(config.allFieldKeys || {}).forEach(function(fieldKey) {
            const rule = jobRules[fieldKey] || null;
            const visible = evaluateVisibility(rule, months);
            const required = visible && evaluateRequired(rule, months, fieldKey, defaults);
            setFieldVisibility(fieldKey, visible);
            setFieldRequired(fieldKey, required);
        });
        document.querySelectorAll('.form-section').forEach(function(section) {
            const fields = section.querySelectorAll('[data-recruitment-field]');
            if (!fields.length) return;
            const anyVisible = Array.prototype.some.call(fields, function(field) {
                return field.style.display !== 'none';
            });
            section.style.display = anyVisible ? '' : 'none';
        });
        updateFieldHelpTexts(config);
    }

    function updateFieldHelpTexts(config) {
        const jobId = getSelectedJobId();
        const jobRules = jobId && config.jobRules && config.jobRules[jobId] ? config.jobRules[jobId] : {};
        Object.keys(config.allFieldKeys || {}).forEach(function(fieldKey) {
            const text = ((jobRules[fieldKey] && jobRules[fieldKey].help_text) || '').trim();
            document.querySelectorAll(`[data-recruitment-field="${fieldKey}"]`).forEach(function(wrapper) {
                let help = wrapper.querySelector('.field-explanation-text');
                if (!help) {
                    help = document.createElement('small');
                    help.className = 'field-explanation-text';
                    wrapper.appendChild(help);
                }
                help.textContent = text;
                help.style.display = text ? '' : 'none';
            });
        });
    }

    function rebuildLimitationTemplateOptions(config) {
        const templateSelect = document.querySelector('[data-limitation-template]');
        if (!templateSelect) return;

        const jobId = getSelectedJobId();
        const currentValue = templateSelect.value;
        const textField = document.querySelector('[data-limitation-text]');

        templateSelect.innerHTML = '';
        const emptyOption = document.createElement('option');
        emptyOption.value = '';
        emptyOption.textContent = '-Empty-';
        templateSelect.appendChild(emptyOption);

        const reasons = (config.limitationReasons || []).filter(function(reason) {
            if (!jobId) return true;
            if (reason.applies_to_all_jobs) return true;
            return (reason.job_ids || []).map(String).includes(String(jobId));
        });

        reasons.forEach(function(reason) {
            const option = document.createElement('option');
            option.value = String(reason.id);
            option.textContent = reason.title;
            option.dataset.templateText = reason.text || '';
            templateSelect.appendChild(option);
        });

        if (currentValue && Array.from(templateSelect.options).some(function(opt) { return opt.value === currentValue; })) {
            templateSelect.value = currentValue;
        } else {
            templateSelect.value = '';
        }
    }

    function applyLimitationTemplate(config) {
        const templateSelect = document.querySelector('[data-limitation-template]');
        const textField = document.querySelector('[data-limitation-text]');
        if (!templateSelect || !textField) return;

        if (!templateSelect.value) {
            return;
        }

        const selected = templateSelect.options[templateSelect.selectedIndex];
        if (selected && selected.dataset.templateText !== undefined) {
            textField.value = selected.dataset.templateText;
        }
    }

    function getMonthlySalaryInput() {
        return document.querySelector('[data-recruitment-monthly-salary]');
    }

    function payscaleSelectionComplete(selects) {
        const group = selects.group ? selects.group.value : '';
        const level = selects.level ? selects.level.value : '';
        return Boolean(group && level);
    }

    function getPayscaleSelects() {
        return {
            group: document.querySelector('[data-recruitment-payscale-group]'),
            level: document.querySelector('[data-recruitment-experience-level]'),
        };
    }

    function rebuildExperienceLevelOptions(config, group, selectedLevel) {
        const levelSelect = getPayscaleSelects().level;
        if (!levelSelect) {
            return;
        }
        const currentValue = selectedLevel !== undefined && selectedLevel !== null
            ? String(selectedLevel)
            : levelSelect.value;
        levelSelect.innerHTML = '<option value="">— Select experience level —</option>';
        if (group && config.payscaleData && config.payscaleData[group]) {
            config.payscaleData[group].forEach(function(item) {
                const opt = document.createElement('option');
                opt.value = String(item.experience_level);
                opt.textContent = String(item.experience_level);
                levelSelect.appendChild(opt);
            });
        }
        if (currentValue) {
            levelSelect.value = currentValue;
        }
    }

    function lookupSalary(config, group, level) {
        if (!group || level === null || level === undefined || level === '' || !config.payscaleData) {
            return null;
        }
        const parsedLevel = parseInt(level, 10);
        if (isNaN(parsedLevel)) {
            return null;
        }
        const groupEntries = config.payscaleData[group];
        if (!groupEntries) {
            return null;
        }
        const match = groupEntries.find(function(item) {
            return item.experience_level === parsedLevel;
        });
        return match ? match.monthly_salary : null;
    }

    function getWeeklyHoursInput() {
        return document.querySelector('[data-recruitment-weekly-hours], [name="weekly_hours"]');
    }

    function updateJobHelpText(config) {
        const helpEl = document.getElementById('recruitment-job-help-text');
        if (!helpEl) {
            return;
        }
        const jobId = getSelectedJobId();
        let text = '';
        if (jobId && config.jobPayscale && config.jobPayscale[jobId]) {
            text = (config.jobPayscale[jobId].help_text || '').trim();
        }
        if (text) {
            helpEl.textContent = text;
            helpEl.style.display = '';
        } else {
            helpEl.textContent = '';
            helpEl.style.display = 'none';
        }
    }

    function applyJobPayscaleDefaults(config, options) {
        const force = options && options.force;
        const selects = getPayscaleSelects();
        const salaryInput = getMonthlySalaryInput();
        const jobId = getSelectedJobId();
        updateJobHelpText(config);
        if (!jobId || !config.jobPayscale) {
            return;
        }
        const jobData = config.jobPayscale[jobId];
        if (!jobData) {
            return;
        }

        // Fixed estimated salary on job (no TV-L): fill monthly salary, clear TV-L.
        if (jobData.has_fixed_estimate && jobData.estimated_salary) {
            if (selects.group) {
                selects.group.value = '';
            }
            if (selects.level) {
                rebuildExperienceLevelOptions(config, '', '');
            }
            if (salaryInput && (force || !salaryInput.value)) {
                salaryInput.value = jobData.estimated_salary;
            }
            return;
        }

        if (!selects.group || !selects.level) {
            return;
        }
        if (force || !selects.group.value) {
            selects.group.value = jobData.pay_scale_group || '';
        }
        const group = selects.group.value;
        const preferredLevel = force
            ? (jobData.experience_level !== null && jobData.experience_level !== undefined
                ? String(jobData.experience_level)
                : '')
            : (selects.level.value || jobData.experience_level);
        rebuildExperienceLevelOptions(config, group, preferredLevel);
        if (force || !selects.level.value) {
            if (jobData.experience_level !== null && jobData.experience_level !== undefined) {
                selects.level.value = String(jobData.experience_level);
            } else if (force) {
                selects.level.value = '';
            }
        }
    }

    function updateWorkloadPercentHint() {
        const hoursInput = getWeeklyHoursInput();
        const percentEl = document.getElementById('recruitment-workload-percent');
        const hintEl = document.getElementById('recruitment-monthly-costs-hint');
        if (!percentEl) {
            return;
        }
        const defaultHours = parseFloat(
            (hintEl && hintEl.getAttribute('data-default-weekly-hours'))
            || (document.getElementById('recruitment-default-weekly-hours') || {}).textContent
            || '39'
        );
        if (!hoursInput || !String(hoursInput.value || '').trim()) {
            percentEl.textContent = '100% (default full-time)';
            return;
        }
        const hours = parseFloat(String(hoursInput.value).replace(',', '.'));
        if (isNaN(hours) || isNaN(defaultHours) || defaultHours <= 0) {
            percentEl.textContent = '—';
            return;
        }
        const pct = (hours / defaultHours) * 100;
        percentEl.textContent = pct.toFixed(1) + '%';
    }

    function updateMonthlyCostsHint() {
        const salaryInput = getMonthlySalaryInput();
        const hoursInput = getWeeklyHoursInput();
        const valueEl = document.getElementById('recruitment-monthly-costs-value');
        const hintEl = document.getElementById('recruitment-monthly-costs-hint');
        if (!valueEl || !hintEl) {
            return;
        }
        const mult = parseFloat(hintEl.getAttribute('data-true-cost-multiplicator') || '1.3');
        const defaultHours = parseFloat(hintEl.getAttribute('data-default-weekly-hours') || '39');
        const salary = salaryInput ? parseFloat(String(salaryInput.value).replace(',', '.')) : NaN;
        let fraction = 1;
        if (hoursInput && String(hoursInput.value || '').trim()) {
            const hours = parseFloat(String(hoursInput.value).replace(',', '.'));
            if (!isNaN(hours) && !isNaN(defaultHours) && defaultHours > 0) {
                fraction = hours / defaultHours;
            }
        }
        updateWorkloadPercentHint();
        if (!isNaN(salary) && !isNaN(mult)) {
            valueEl.textContent = (salary * fraction * mult).toFixed(2) + ' €';
        } else {
            valueEl.textContent = '—';
        }
    }

    function syncMonthlySalaryField(config) {
        const salaryInput = getMonthlySalaryInput();
        const selects = getPayscaleSelects();
        if (!salaryInput) {
            updateMonthlyCostsHint();
            return;
        }
        if (selects.group && selects.level && payscaleSelectionComplete(selects)) {
            const salary = lookupSalary(
                config,
                selects.group.value,
                selects.level.value,
            );
            if (salary !== null) {
                salaryInput.value = salary;
            }
            salaryInput.readOnly = true;
            salaryInput.classList.add('form-readonly');
            updateMonthlyCostsHint();
            return;
        }
        salaryInput.readOnly = false;
        salaryInput.classList.remove('form-readonly');
        updateMonthlyCostsHint();
    }

    function initPayscaleFields(config) {
        const selects = getPayscaleSelects();
        if (!selects.group || !selects.level) {
            return;
        }
        if (selects.group.value) {
            rebuildExperienceLevelOptions(config, selects.group.value, selects.level.value);
        }
        selects.group.addEventListener('change', function() {
            rebuildExperienceLevelOptions(config, selects.group.value, '');
            syncMonthlySalaryField(config);
        });
        selects.level.addEventListener('change', function() {
            syncMonthlySalaryField(config);
        });
    }

    function initJobDropdownHover(config) {
        const select = document.querySelector('[data-recruitment-job]');
        if (!select || select.dataset.customDropdown === 'true') {
            return;
        }
        if (!config.jobPayscale) {
            return;
        }
        select.dataset.customDropdown = 'true';
        const wrapper = document.createElement('div');
        wrapper.className = 'job-custom-select';
        select.parentNode.insertBefore(wrapper, select);
        wrapper.appendChild(select);
        select.classList.add('job-native-select');

        const toggle = document.createElement('button');
        toggle.type = 'button';
        toggle.className = 'job-select-toggle form-control';
        toggle.setAttribute('aria-haspopup', 'listbox');

        const menu = document.createElement('ul');
        menu.className = 'job-select-menu';
        menu.setAttribute('role', 'listbox');

        const tooltip = document.createElement('div');
        tooltip.className = 'job-hover-tooltip';
        tooltip.hidden = true;

        function selectedLabel() {
            const option = select.options[select.selectedIndex];
            return option ? option.textContent : '— Select job —';
        }

        function hideTooltip() {
            tooltip.hidden = true;
            tooltip.textContent = '';
        }

        function rebuildMenu() {
            menu.innerHTML = '';
            Array.prototype.forEach.call(select.options, function(option) {
                const item = document.createElement('li');
                item.setAttribute('role', 'option');
                item.dataset.value = option.value;
                item.textContent = option.textContent;
                const jobData = option.value && config.jobPayscale[option.value];
                const hoverText = jobData ? (jobData.dropdown_help_text || '').trim() : '';
                item.dataset.hover = hoverText;
                if (option.value === select.value) {
                    item.classList.add('is-selected');
                }
                item.addEventListener('mouseenter', function() {
                    if (hoverText) {
                        tooltip.textContent = hoverText;
                        tooltip.hidden = false;
                    } else {
                        hideTooltip();
                    }
                });
                item.addEventListener('mouseleave', hideTooltip);
                item.addEventListener('click', function() {
                    select.value = option.value;
                    toggle.textContent = option.textContent;
                    menu.classList.remove('is-open');
                    hideTooltip();
                    select.dispatchEvent(new Event('change', { bubbles: true }));
                });
                menu.appendChild(item);
            });
            toggle.textContent = selectedLabel();
        }

        toggle.addEventListener('click', function(event) {
            event.preventDefault();
            menu.classList.toggle('is-open');
        });
        document.addEventListener('click', function(event) {
            if (!wrapper.contains(event.target)) {
                menu.classList.remove('is-open');
                hideTooltip();
            }
        });

        wrapper.appendChild(toggle);
        wrapper.appendChild(menu);
        wrapper.appendChild(tooltip);
        rebuildMenu();
        select.addEventListener('change', function() {
            toggle.textContent = selectedLabel();
        });
    }

    window.initRecruitmentDynamicForm = function(config) {
        if (!config) return;

        function refresh(options) {
            if (config.enableJobRules) {
                applyJobFieldRules(config);
            }
            if (config.enableLimitationTemplates) {
                rebuildLimitationTemplateOptions(config);
            }
            applyJobPayscaleDefaults(config, options);
            syncMonthlySalaryField(config);
        }

        initPayscaleFields(config);
        initJobDropdownHover(config);

        document.addEventListener('change', function(event) {
            if (event.target.matches('[data-recruitment-job]')) {
                refresh({ force: true });
            }
            if (event.target.matches('[data-recruitment-payscale-group], [data-recruitment-experience-level]')) {
                syncMonthlySalaryField(config);
            }
            if (event.target.matches('[data-contract-date], [name="valid_from"], [name="valid_until"]')) {
                if (config.enableJobRules) {
                    applyJobFieldRules(config);
                }
            }
            if (event.target.matches('[data-limitation-template]')) {
                applyLimitationTemplate(config);
            }
            if (config.enableJobRules && event.target.closest('[data-recruitment-field]')) {
                applyJobFieldRules(config);
            }
        });

        document.addEventListener('input', function(event) {
            if (event.target.matches('[data-contract-date], [name="valid_from"], [name="valid_until"]')) {
                if (config.enableJobRules) {
                    applyJobFieldRules(config);
                }
            }
            if (event.target.matches(
                '[data-recruitment-monthly-salary], [name="monthly_salary"], '
                + '[data-recruitment-weekly-hours], [name="weekly_hours"]'
            )) {
                updateMonthlyCostsHint();
            }
            if (config.enableJobRules && event.target.closest('[data-recruitment-field]')) {
                applyJobFieldRules(config);
            }
        });

        refresh();
        updateMonthlyCostsHint();
    };
})();