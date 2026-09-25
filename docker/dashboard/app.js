// Coriolis Web Dashboard Application Logic with Multi-Language Support (DE / EN)

const API_BASE = '/v1/admin';

const TRANSLATIONS = {
    de: {
        "nav-dashboard": "Dashboard",
        "nav-endpoints": "Endpunkte",
        "nav-transfers": "Migrationen",
        "nav-services": "Systemdienste",
        "api-status": "Coriolis API",
        "card-endpoints": "Endpunkte",
        "card-transfers": "Migrationen",
        "card-worker": "Worker Status",
        "active-transfers": "Aktive Migrationen",
        "view-all": "Alle anzeigen",
        "th-id": "ID",
        "th-vms": "VMs",
        "th-source": "Quelle (VMware)",
        "th-target": "Ziel (OLVM)",
        "th-status": "Status",
        "th-actions": "Aktionen",
        "title-endpoints": "Registrierte Endpunkte",
        "btn-add-endpoint": "+ Endpunkt hinzufügen",
        "title-transfers": "Migrations-Jobs",
        "btn-create-transfer": "+ Migration erstellen",
        "title-services": "Coriolis Systemdienste",
        "th-service": "Dienst",
        "th-host": "Host / Container",
        "th-updated": "Zuletzt aktualisiert",
        
        "modal-ep-title": "Neuen Endpunkt registrieren",
        "label-ep-name": "Endpunkt Name",
        "label-ep-type": "Endpunkt Typ",
        "opt-ep-vmware": "VMware vSphere",
        "opt-ep-olvm": "Oracle OLVM",
        "opt-ep-hyperv": "Microsoft Hyper-V",
        "opt-ep-proxmox": "Proxmox VE",
        "label-proxmox-url": "Proxmox API URL",
        "placeholder-proxmox-url": "https://pve.firma.local:8006/api2/json",
        "placeholder-proxmox-user": "root@pam",
        "label-tf-proxmox-node": "Ziel-Node (in Proxmox)",
        "placeholder-tf-proxmox-node": "z.B. pve1",
        "label-tf-proxmox-storage": "Ziel-Storage",
        "placeholder-tf-proxmox-storage": "z.B. local-lvm",
        "label-tf-datacenter": "Ziel-Datacenter (in vSphere)",
        "placeholder-tf-datacenter": "z.B. Datacenter",
        "label-tf-cluster-compute": "Ziel-Cluster",
        "placeholder-tf-cluster-compute": "z.B. Cluster",
        "label-tf-datastore": "Ziel-Datastore",
        "placeholder-tf-datastore": "z.B. datastore1",
        "label-vcenter-host": "vCenter Host / IP",
        "label-username": "Benutzername",
        "label-password": "Passwort",
        "label-ignore-ssl": "SSL Zertifikat ignorieren (allow_untrusted)",
        "label-ignore-ssl-winrm": "WinRM Zertifikat ignorieren",
        "label-olvm-url": "OLVM Engine API URL",
        "label-hyperv-host": "Hyper-V Host / IP",
        "label-hyperv-port": "WinRM Port",
        "label-hyperv-transport": "WinRM Transport",
        "label-hyperv-https": "HTTPS verwenden (WinRM 5986)",
        "btn-cancel": "Abbrechen",
        "btn-register": "Registrieren",
        
        "modal-tf-title": "Migration erstellen",
        "label-tf-source": "Quell-Endpunkt",
        "label-tf-dest": "Ziel-Endpunkt",
        "label-tf-hyperv-dest": "Ziel (Hyper-V Endpunkt)",
        "label-tf-vms": "VM Name (im Quellsystem)",
        "label-tf-cluster": "Ziel-Cluster (in OLVM)",
        "label-tf-storage": "Ziel-Storage Domain",
        "label-tf-network": "Netzwerk-Zuweisung (Quell-Netz -> Ziel-Netz)",
        "label-tf-storage-map": "Storage-Zuweisung (Quell-Datastore -> Ziel-Domain)",
        "btn-add-storage-mapping": "+ Zuweisung hinzufügen",
        "label-tf-preserve-mac": "MAC-Adressen der Quell-VM beibehalten",
        "btn-create": "Erstellen",
        
        "select-please": "Bitte wählen...",
        "status-healthy": "Gesund",
        "status-warning": "Warnung",
        "status-no-services": "Keine Dienste",
        "status-online": "Online",
        "status-offline": "Offline",
        "status-unknown": "Unbekannt",
        
        "placeholder-ep-name": "z.B. vcenter-prod-01",
        "placeholder-vmware-host": "z.B. vcenter.firma.local",
        "placeholder-vmware-user": "administrator@vsphere.local",
        "placeholder-olvm-url": "https://olvm-engine.firma.local/ovirt-engine/",
        "placeholder-olvm-user": "admin@internal",
        "placeholder-hyperv-host": "z.B. hyperv-host.firma.local",
        "placeholder-hyperv-user": "Administrator",
        "label-tf-switch": "Ziel Virtual Switch",
        "label-tf-vmpath": "Ziel VM-Pfad (auf dem Host)",
        "label-tf-generation": "VM Generation",
        "placeholder-tf-switch": "z.B. External",
        "placeholder-tf-vmpath": "C:\\VMs",
        "placeholder-tf-vms": "z.B. webserver-prod-01",
        "placeholder-tf-cluster": "z.B. Default",
        "placeholder-tf-storage": "z.B. data",
        "placeholder-source-net": "z.B. VM Network",
        "placeholder-dest-net": "z.B. ovirtmgmt",
        "placeholder-source-store": "z.B. datastore1",
        "placeholder-dest-store": "z.B. data",
        
        "msg-loading": "Lade Daten...",
        "msg-no-endpoints": "Keine registrierten Endpunkte vorhanden.",
        "msg-no-transfers": "Keine Migrations-Jobs vorhanden.",
        "msg-no-services": "Keine Systemdienste registriert.",
        "msg-action-running": "In Ausführung...",
        "msg-no-execution": "Keine Ausführungsdaten vorhanden.",
        "title-execution": "Ausführung",
        
        "btn-replication": "Replikation",
        "btn-cutover": "Cutover",
        "btn-delete": "Löschen",
        "btn-clean": "Bereinigen",
        
        "confirm-delete-ep": "Möchten Sie diesen Endpunkt wirklich löschen?",
        "confirm-delete-tf": "Möchten Sie diesen Migrations-Job wirklich löschen?",
        "confirm-delete-service": "Möchten Sie diesen inaktiven Dienst-Eintrag aus der Datenbank löschen?",
        "confirm-deploy": "Möchten Sie das finale Deployment starten? Die VMware VM wird dabei heruntergefahren.",
        
        "alert-ep-success": "Endpunkt erfolgreich registriert!",
        "alert-tf-success": "Migrations-Job erfolgreich erstellt!",
        "alert-repl-success": "Replikations-Schritt erfolgreich gestartet!",
        "alert-deploy-success": "Cutover-Deployment erfolgreich gestartet!",
        "alert-error-ep": "Fehler beim Erstellen des Endpunkts",
        "alert-error-tf": "Fehler beim Erstellen der Migration",
        "alert-error-delete": "Fehler beim Löschen",
        "alert-error-repl": "Fehler beim Starten der Replikation",
        "alert-error-deploy": "Fehler beim Starten des Deployments",
        "alert-error-service": "Fehler beim Löschen des Dienstes",
        
        "title-dashboard-overview": "Dashboard Übersicht",
        "title-endpoint-management": "Endpunkt Management",
        "title-migration-tasks": "Migrations-Jobs",
        "title-coriolis-services": "Coriolis Systemdienste",
        
        "badge-vmware": "VMware vSphere",
        "badge-olvm": "Oracle OLVM",
        "badge-hyperv": "Microsoft Hyper-V",
        "badge-proxmox": "Proxmox VE",
        "ep-created-via-dashboard": "Endpunkt registriert via Dashboard",
                "status-up": "Aktiv (UP)",
        "status-down": "Down",
        "btn-edit": "Bearbeiten",
        "modal-ep-title-edit": "Endpunkt bearbeiten",
        "alert-ep-update-success": "Endpunkt erfolgreich aktualisiert!",
        "alert-error-ep-update": "Fehler beim Aktualisieren des Endpunkts",
        
        "nav-configs": "Konfiguration",
        "nav-faq": "FAQ",
        "nav-api": "API Docs",
        "title-configs": "Konfigurationsdateien",
        "title-faq": "Häufig gestellte Fragen (FAQ)",
        "label-select-config": "Datei auswählen",
        "label-config-content": "Dateiinhalt",
        "btn-save-config": "Speichern",
        "placeholder-config-select": "Bitte wählen Sie eine Konfigurationsdatei aus...",
        "alert-config-load-success": "Konfiguration erfolgreich geladen!",
        "alert-config-save-success": "Konfiguration erfolgreich gespeichert!",
        "alert-error-config-load": "Fehler beim Laden der Konfiguration",
        "title-configs-editor": "Konfigurations-Editor",
        "title-faq-section": "Häufig gestellte Fragen",
        "login-subtitle": "CloudShift Migrations-Dashboard",
        "label-login-username": "Benutzername",
        "label-login-password": "Passwort",
        "btn-login": "Anmelden",
        "btn-logout-title": "Abmelden",
        "login-hint": "Lokal (admin/operator/viewer) oder LDAPS / Active Directory",
        "login-error-empty": "Bitte Benutzername und Passwort eingeben.",
        "login-error-failed": "Ungültige Anmeldedaten oder Server nicht erreichbar.",
        "session-expired": "Sitzung abgelaufen. Bitte erneut anmelden.",
        "role-viewer-notice": "Sie sind als Betrachter (Viewer) angemeldet. Änderungen und Migrationen sind deaktiviert.",
        "role-operator-notice": "Sie sind als Operator angemeldet.",
        "role-admin-notice": "Sie sind als Administrator angemeldet."
    },
    en: {
        "nav-dashboard": "Dashboard",
        "nav-endpoints": "Endpoints",
        "nav-transfers": "Migrations",
        "nav-services": "System Services",
        "api-status": "Coriolis API",
        "card-endpoints": "Endpoints",
        "card-transfers": "Migrations",
        "card-worker": "Worker Status",
        "active-transfers": "Active Migrations",
        "view-all": "View All",
        "th-id": "ID",
        "th-vms": "VMs",
        "th-source": "Source (VMware)",
        "th-target": "Target (OLVM)",
        "th-status": "Status",
        "th-actions": "Actions",
        "title-endpoints": "Registered Endpoints",
        "btn-add-endpoint": "+ Add Endpoint",
        "title-transfers": "Migration Jobs",
        "btn-create-transfer": "+ Create Migration",
        "title-services": "Coriolis System Services",
        "th-service": "Service",
        "th-host": "Host / Container",
        "th-updated": "Last Updated",
        
        "modal-ep-title": "Register New Endpoint",
        "label-ep-name": "Endpoint Name",
        "label-ep-type": "Endpoint Type",
        "opt-ep-vmware": "VMware vSphere",
        "opt-ep-olvm": "Oracle OLVM",
        "opt-ep-hyperv": "Microsoft Hyper-V",
        "opt-ep-proxmox": "Proxmox VE",
        "label-proxmox-url": "Proxmox API URL",
        "placeholder-proxmox-url": "https://pve.company.local:8006/api2/json",
        "placeholder-proxmox-user": "root@pam",
        "label-tf-proxmox-node": "Target Node (in Proxmox)",
        "placeholder-tf-proxmox-node": "e.g. pve1",
        "label-tf-proxmox-storage": "Target Storage",
        "placeholder-tf-proxmox-storage": "e.g. local-lvm",
        "label-tf-datacenter": "Target Datacenter (in vSphere)",
        "placeholder-tf-datacenter": "e.g. Datacenter",
        "label-tf-cluster-compute": "Target Cluster",
        "placeholder-tf-cluster-compute": "e.g. Cluster",
        "label-tf-datastore": "Target Datastore",
        "placeholder-tf-datastore": "e.g. datastore1",
        "label-vcenter-host": "vCenter Host / IP",
        "label-username": "Username",
        "label-password": "Password",
        "label-ignore-ssl": "Ignore SSL Certificate (allow_untrusted)",
        "label-ignore-ssl-winrm": "Ignore WinRM Certificate",
        "label-olvm-url": "OLVM Engine API URL",
        "label-hyperv-host": "Hyper-V Host / IP",
        "label-hyperv-port": "WinRM Port",
        "label-hyperv-transport": "WinRM Transport",
        "label-hyperv-https": "Use HTTPS (WinRM 5986)",
        "btn-cancel": "Cancel",
        "btn-register": "Register",
        
        "modal-tf-title": "Create Migration",
        "label-tf-source": "Source Endpoint",
        "label-tf-dest": "Target Endpoint",
        "label-tf-hyperv-dest": "Target (Hyper-V Endpoint)",
        "label-tf-vms": "VM Name (in source platform)",
        "label-tf-cluster": "Target Cluster (in OLVM)",
        "label-tf-storage": "Target Storage Domain",
        "label-tf-network": "Network Mapping (Source Net -> Target Net)",
        "label-tf-storage-map": "Storage Mapping (Source Datastore -> Target Domain)",
        "btn-add-storage-mapping": "+ Add Storage Mapping",
        "label-tf-preserve-mac": "Preserve source VM MAC addresses",
        "btn-create": "Create",
        
        "select-please": "Please select...",
        "status-healthy": "Healthy",
        "status-warning": "Warning",
        "status-no-services": "No Services",
        "status-online": "Online",
        "status-offline": "Offline",
        "status-unknown": "Unknown",
        
        "placeholder-ep-name": "e.g. vcenter-prod-01",
        "placeholder-vmware-host": "e.g. vcenter.company.local",
        "placeholder-vmware-user": "administrator@vsphere.local",
        "placeholder-olvm-url": "https://olvm-engine.company.local/ovirt-engine/",
        "placeholder-olvm-user": "admin@internal",
        "placeholder-hyperv-host": "e.g. hyperv-host.company.local",
        "placeholder-hyperv-user": "Administrator",
        "label-tf-switch": "Target Virtual Switch",
        "label-tf-vmpath": "Target VM Path (on host)",
        "label-tf-generation": "VM Generation",
        "placeholder-tf-switch": "e.g. External",
        "placeholder-tf-vmpath": "C:\\VMs",
        "placeholder-tf-vms": "e.g. webserver-prod-01",
        "placeholder-tf-cluster": "e.g. Default",
        "placeholder-tf-storage": "e.g. data",
        "placeholder-source-net": "e.g. VM Network",
        "placeholder-dest-net": "e.g. ovirtmgmt",
        "placeholder-source-store": "e.g. datastore1",
        "placeholder-dest-store": "e.g. data",
        
        "msg-loading": "Loading data...",
        "msg-no-endpoints": "No registered endpoints available.",
        "msg-no-transfers": "No migration tasks available.",
        "msg-no-services": "No system services registered.",
        "msg-action-running": "Executing...",
        "msg-no-execution": "No execution data available.",
        "title-execution": "Execution",
        
        "btn-replication": "Replicate",
        "btn-cutover": "Cutover",
        "btn-delete": "Delete",
        "btn-clean": "Clean",
        
        "confirm-delete-ep": "Are you sure you want to delete this endpoint?",
        "confirm-delete-tf": "Are you sure you want to delete this migration job?",
        "confirm-delete-service": "Are you sure you want to delete this inactive service entry from the database?",
        "confirm-deploy": "Are you sure you want to start the final deployment? The VMware VM will be shut down.",
        
        "alert-ep-success": "Endpoint registered successfully!",
        "alert-tf-success": "Migration job created successfully!",
        "alert-repl-success": "Replication step started successfully!",
        "alert-deploy-success": "Cutover deployment started successfully!",
        "alert-error-ep": "Error registering endpoint",
        "alert-error-tf": "Error creating migration",
        "alert-error-delete": "Error deleting",
        "alert-error-repl": "Error starting replication",
        "alert-error-deploy": "Error starting deployment",
        "alert-error-service": "Error deleting service",
        
        "title-dashboard-overview": "Dashboard Overview",
        "title-endpoint-management": "Endpoint Management",
        "title-migration-tasks": "Migration Tasks",
        "title-coriolis-services": "Coriolis Services",
        
        "badge-vmware": "VMware vSphere",
        "badge-olvm": "Oracle OLVM",
        "badge-hyperv": "Microsoft Hyper-V",
        "badge-proxmox": "Proxmox VE",
        "ep-created-via-dashboard": "Endpoint registered via Dashboard",
        "status-up": "Active (UP)",
        "status-down": "Down",
        "btn-edit": "Edit",
        "modal-ep-title-edit": "Edit Endpoint",
        "alert-ep-update-success": "Endpoint updated successfully!",
        "alert-error-ep-update": "Error updating endpoint",
        
        "nav-configs": "Configuration",
        "nav-faq": "FAQ",
        "nav-api": "API Docs",
        "title-configs": "Configuration Files",
        "title-faq": "Frequently Asked Questions (FAQ)",
        "label-select-config": "Select File",
        "label-config-content": "File Content",
        "btn-save-config": "Save",
        "placeholder-config-select": "Please select a configuration file...",
        "alert-config-load-success": "Configuration loaded successfully!",
        "alert-config-save-success": "Configuration saved successfully!",
        "alert-error-config-load": "Error loading configuration",
        "title-configs-editor": "Configuration Editor",
        "title-faq-section": "Frequently Asked Questions",
        "login-subtitle": "CloudShift Migration Dashboard",
        "label-login-username": "Username",
        "label-login-password": "Password",
        "btn-login": "Sign In",
        "btn-logout-title": "Log out",
        "login-hint": "Local (admin/operator/viewer) or LDAPS / Active Directory",
        "login-error-empty": "Please enter username and password.",
        "login-error-failed": "Invalid credentials or server unreachable.",
        "session-expired": "Session expired. Please sign in again.",
        "role-viewer-notice": "You are logged in with Read-Only (Viewer) access. Modifications are disabled.",
        "role-operator-notice": "You are logged in as Operator.",
        "role-admin-notice": "You are logged in as Administrator."
    }
};

let currentLang = localStorage.getItem('coriolis_lang') || (navigator.language.startsWith('de') ? 'de' : 'en');
let registeredEndpoints = [];
let editingEndpointId = null;
let expandedTransferIds = [];
let lastTransfersData = [];
let lastEndpointsData = [];

document.addEventListener('DOMContentLoaded', () => {
    initApp();
});

function getAuthToken() {
    return sessionStorage.getItem('coriolis_token');
}

function setAuthToken(token, user) {
    if (token) {
        sessionStorage.setItem('coriolis_token', token);
        sessionStorage.setItem('coriolis_user', JSON.stringify(user || {}));
    } else {
        sessionStorage.removeItem('coriolis_token');
        sessionStorage.removeItem('coriolis_user');
    }
}

function getStoredUser() {
    try {
        const raw = sessionStorage.getItem('coriolis_user');
        return raw ? JSON.parse(raw) : null;
    } catch (e) {
        return null;
    }
}

async function fetchWithAuth(url, options = {}) {
    const token = getAuthToken();
    const headers = options.headers ? new Headers(options.headers) : new Headers();

    if (token) {
        headers.set('Authorization', `Bearer ${token}`);
    }

    const response = await fetch(url, { ...options, headers });

    // Handle 401 Unauthorized globally
    if (response.status === 401 && !url.includes('/auth/login')) {
        showLoginModal(getTranslation('session-expired'));
    }

    return response;
}

function showLoginModal(errorMessage = '') {
    const overlay = document.getElementById('loginOverlay');
    const errorEl = document.getElementById('loginError');
    if (!overlay) return;
    if (errorMessage) {
        errorEl.textContent = errorMessage;
        errorEl.classList.remove('hidden');
    } else {
        errorEl.classList.add('hidden');
        errorEl.textContent = '';
    }
    overlay.classList.add('active');
    const pw = document.getElementById('loginPassword');
    if (pw) pw.value = '';
}

function hideLoginModal() {
    const overlay = document.getElementById('loginOverlay');
    if (overlay) overlay.classList.remove('active');
}

async function performLogin(username, password) {
    const errorEl = document.getElementById('loginError');
    const spinner = document.getElementById('loginSpinner');
    const submitBtn = document.getElementById('btnLoginSubmit');

    if (errorEl) {
        errorEl.classList.add('hidden');
        errorEl.textContent = '';
    }
    if (spinner) spinner.classList.remove('hidden');
    if (submitBtn) submitBtn.disabled = true;

    try {
        const res = await fetch('/v1/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });

        const data = await res.json();
        if (!res.ok) {
            const msg = (data.error && data.error.message) || data.explanation || getTranslation('login-error-failed');
            throw new Error(msg);
        }

        setAuthToken(data.token, data.user);
        hideLoginModal();
        updateUserProfile(data.user);
        applyRolePermissions(data.user.roles || []);
        await refreshAllData();
        fetchConfigsList();
    } catch (err) {
        if (errorEl) {
            errorEl.textContent = err.message || getTranslation('login-error-failed');
            errorEl.classList.remove('hidden');
        }
    } finally {
        if (spinner) spinner.classList.add('hidden');
        if (submitBtn) submitBtn.disabled = false;
    }
}

function performLogout() {
    setAuthToken(null, null);
    showLoginModal();
    updateUserProfile(null);
    applyRolePermissions(['viewer']);
}

function updateUserProfile(user) {
    if (!user) {
        user = { username: 'Gast', roles: ['viewer'] };
    }
    const avatarEl = document.getElementById('userAvatar');
    const nameEl = document.getElementById('userName');
    const roleBadgeEl = document.getElementById('userRoleBadge');

    if (nameEl) nameEl.textContent = user.name || user.username || 'User';
    if (avatarEl) avatarEl.textContent = (user.username || 'U')[0].toUpperCase();

    if (roleBadgeEl) {
        const roles = user.roles || ['viewer'];
        roleBadgeEl.className = 'user-role';
        if (roles.includes('admin')) {
            roleBadgeEl.textContent = 'admin';
            roleBadgeEl.classList.add('badge-admin');
        } else if (roles.includes('operator')) {
            roleBadgeEl.textContent = 'operator';
            roleBadgeEl.classList.add('badge-operator');
        } else {
            roleBadgeEl.textContent = 'viewer';
            roleBadgeEl.classList.add('badge-viewer');
        }
    }
}

function applyRolePermissions(roles = []) {
    const isAdmin = roles.includes('admin');
    const isOperator = roles.includes('operator') || isAdmin;
    const isViewerOnly = !isOperator;

    const banner = document.getElementById('roleNoticeBanner');
    if (banner) {
        if (isViewerOnly) {
            banner.textContent = `ℹ️ ${getTranslation('role-viewer-notice')}`;
            banner.classList.remove('hidden');
        } else {
            banner.classList.add('hidden');
        }
    }

    const btnNewEndpoint = document.getElementById('btnNewEndpoint');
    const btnNewTransfer = document.getElementById('btnNewTransfer');
    const btnSaveConfig = document.getElementById('btnSaveConfig');

    if (btnNewEndpoint) {
        btnNewEndpoint.disabled = isViewerOnly;
        btnNewEndpoint.title = isViewerOnly ? getTranslation('role-viewer-notice') : '';
    }
    if (btnNewTransfer) {
        btnNewTransfer.disabled = isViewerOnly;
        btnNewTransfer.title = isViewerOnly ? getTranslation('role-viewer-notice') : '';
    }
    if (btnSaveConfig) {
        btnSaveConfig.disabled = !isAdmin;
        btnSaveConfig.title = !isAdmin ? 'Nur für Administratoren' : '';
    }
}

function initApp() {
    setupNavigation();
    setupModals();
    setupForms();
    setupLangSelector();
    setupConfigEditor();

    // Check existing authentication token
    const token = getAuthToken();
    const storedUser = getStoredUser();

    if (!token) {
        showLoginModal();
    } else {
        hideLoginModal();
        updateUserProfile(storedUser);
        applyRolePermissions(storedUser ? storedUser.roles : []);
        refreshAllData();
        fetchConfigsList();
    }

    // Set connection status label
    document.getElementById('apiHost').textContent = `${window.location.hostname}:7667`;

    // Periodic refresh every 10 seconds only when logged in
    setInterval(() => {
        if (getAuthToken()) {
            refreshAllData();
        }
    }, 10000);
}

function getTranslation(key) {
    if (TRANSLATIONS[currentLang] && TRANSLATIONS[currentLang][key]) {
        return TRANSLATIONS[currentLang][key];
    }
    return key;
}

function translatePage() {
    // Translate all elements with data-i18n attribute
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        const translation = getTranslation(key);
        if (translation !== key) {
            el.textContent = translation;
        }
    });

    // Translate all elements with data-i18n-placeholder attribute
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
        const key = el.getAttribute('data-i18n-placeholder');
        const translation = getTranslation(key);
        if (translation !== key) {
            el.placeholder = translation;
        }
    });

    // Update active tab title in header
    const activeTab = document.querySelector('.nav-item.active');
    if (activeTab) {
        const tabId = activeTab.getAttribute('data-tab');
        updateHeaderTitle(tabId);
    }
    
    // Dynamically render FAQ
    if (typeof renderFaq === 'function') {
        renderFaq();
    }
}

function updateHeaderTitle(tabId) {
    const pageTitle = document.getElementById('pageTitle');
    const titleKeys = {
        dashboard: 'title-dashboard-overview',
        endpoints: 'title-endpoint-management',
        transfers: 'title-migration-tasks',
        services: 'title-coriolis-services',
        configs: 'title-configs-editor',
        faq: 'title-faq-section',
        swagger: 'nav-api'
    };
    pageTitle.textContent = getTranslation(titleKeys[tabId]);
}

// Language Selector Handling
function setupLangSelector() {
    const btnDe = document.getElementById('btnLangDe');
    const btnEn = document.getElementById('btnLangEn');

    const updateSelectorUI = () => {
        if (currentLang === 'de') {
            btnDe.classList.add('active');
            btnEn.classList.remove('active');
        } else {
            btnDe.classList.remove('active');
            btnEn.classList.add('active');
        }
    };

    if (!btnDe || !btnEn) return;

    btnDe.addEventListener('click', () => {
        currentLang = 'de';
        localStorage.setItem('coriolis_lang', currentLang);
        updateSelectorUI();
        translatePage();
        refreshAllData();
    });

    btnEn.addEventListener('click', () => {
        currentLang = 'en';
        localStorage.setItem('coriolis_lang', currentLang);
        updateSelectorUI();
        translatePage();
        refreshAllData();
    });

    updateSelectorUI();
    translatePage();
}

// Navigation Tabs
function setupNavigation() {
    const navItems = document.querySelectorAll('.nav-item');
    const tabContents = document.querySelectorAll('.tab-content');

    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const tabId = item.getAttribute('data-tab');

            navItems.forEach(nav => nav.classList.remove('active'));
            tabContents.forEach(tab => tab.classList.remove('active'));

            item.classList.add('active');
            document.getElementById(`${tabId}Tab`).classList.add('active');
            
            updateHeaderTitle(tabId);
            window.location.hash = tabId;

            if (tabId === 'configs') {
                fetchConfigsList();
            }
        });
    });

    // Check URL hash on load
    const hash = window.location.hash.substring(1);
    if (hash && document.getElementById(`${hash}Tab`)) {
        const item = document.querySelector(`.nav-item[data-tab="${hash}"]`);
        if (item) item.click();
    }
}

function editEndpoint(id) {
    const ep = registeredEndpoints.find(e => e.id === id);
    if (!ep) return;

    editingEndpointId = id;
    
    // Set title and button text
    document.getElementById('endpointModalTitle').textContent = getTranslation('modal-ep-title-edit');
    document.getElementById('btnSubmitEndpoint').textContent = getTranslation('btn-edit');

    // Populate common fields
    document.getElementById('endpointName').value = ep.name;
    document.getElementById('endpointType').value = ep.type;
    
    // Disable type select during editing
    document.getElementById('endpointType').disabled = true;

     // Show/hide and populate provider-specific fields
    const vmwareFields = document.getElementById('vmwareFields');
    const olvmFields = document.getElementById('olvmFields');
    const hypervFields = document.getElementById('hypervFields');
    const proxmoxFields = document.getElementById('proxmoxFields');

    vmwareFields.classList.add('hidden');
    olvmFields.classList.add('hidden');
    hypervFields.classList.add('hidden');
    proxmoxFields.classList.add('hidden');

    if (ep.type === 'vmware_vsphere') {
        vmwareFields.classList.remove('hidden');
        document.getElementById('vmwareHost').value = ep.connection_info.host || '';
        document.getElementById('vmwareUser').value = ep.connection_info.username || '';
        document.getElementById('vmwarePass').value = ep.connection_info.password || '';
        document.getElementById('vmwareUntrusted').checked = !!ep.connection_info.allow_untrusted;
    } else if (ep.type === 'olvm') {
        olvmFields.classList.remove('hidden');
        document.getElementById('olvmUrl').value = ep.connection_info.url || '';
        document.getElementById('olvmUser').value = ep.connection_info.username || '';
        document.getElementById('olvmPass').value = ep.connection_info.password || '';
        document.getElementById('olvmInsecure').checked = !!ep.connection_info.insecure;
    } else if (ep.type === 'hyperv') {
        hypervFields.classList.remove('hidden');
        document.getElementById('hypervHost').value = ep.connection_info.host || '';
        document.getElementById('hypervPort').value = ep.connection_info.port || 5986;
        document.getElementById('hypervUser').value = ep.connection_info.username || '';
        document.getElementById('hypervPass').value = ep.connection_info.password || '';
        document.getElementById('hypervHttps').checked = ep.connection_info.https !== false;
        document.getElementById('hypervInsecure').checked = ep.connection_info.cert_validation === 'ignore';
        document.getElementById('hypervTransport').value = ep.connection_info.transport || 'ntlm';
    } else if (ep.type === 'proxmox') {
        proxmoxFields.classList.remove('hidden');
        document.getElementById('proxmoxUrl').value = ep.connection_info.url || '';
        document.getElementById('proxmoxUser').value = ep.connection_info.username || '';
        document.getElementById('proxmoxPass').value = ep.connection_info.password || '';
        document.getElementById('proxmoxInsecure').checked = !!ep.connection_info.insecure;
    }

    // Open modal
    document.getElementById('endpointModal').classList.add('active');
}

function resetEndpointModal() {
    editingEndpointId = null;
    document.getElementById('endpointType').disabled = false;
    document.getElementById('endpointForm').reset();
    
    // Reset modal title and submit button text
    document.getElementById('endpointModalTitle').textContent = getTranslation('modal-ep-title');
    document.getElementById('btnSubmitEndpoint').textContent = getTranslation('btn-register');

    // Ensure type change visibility is correct based on default value
    const epType = document.getElementById('endpointType');
    const vmwareFields = document.getElementById('vmwareFields');
    const olvmFields = document.getElementById('olvmFields');
    const hypervFields = document.getElementById('hypervFields');
    const proxmoxFields = document.getElementById('proxmoxFields');

    vmwareFields.classList.add('hidden');
    olvmFields.classList.add('hidden');
    hypervFields.classList.add('hidden');
    proxmoxFields.classList.add('hidden');

    if (epType.value === 'vmware_vsphere') {
        vmwareFields.classList.remove('hidden');
    } else if (epType.value === 'olvm') {
        olvmFields.classList.remove('hidden');
    } else if (epType.value === 'hyperv') {
        hypervFields.classList.remove('hidden');
    } else if (epType.value === 'proxmox') {
        proxmoxFields.classList.remove('hidden');
    }
}

// Modals Handling
function setupModals() {
    const epModal = document.getElementById('endpointModal');
    const btnNewEp = document.getElementById('btnNewEndpoint');
    const btnNewEpClose = document.getElementById('btnChooseEndpointClose');
    const btnCancelEp = document.getElementById('btnCancelEndpoint');

    btnNewEp.addEventListener('click', () => {
        resetEndpointModal();
        epModal.classList.add('active');
    });
    [btnNewEpClose, btnCancelEp].forEach(btn => {
        btn.addEventListener('click', () => {
            resetEndpointModal();
            epModal.classList.remove('active');
        });
    });

    const tfModal = document.getElementById('transferModal');
    const btnNewTf = document.getElementById('btnNewTransfer');
    const btnNewTfClose = document.getElementById('btnChooseTransferClose');
    const btnCancelTf = document.getElementById('btnCancelTransfer');

    btnNewTf.addEventListener('click', () => {
        loadEndpointsForSelect();
        resetStorageMappings();
        tfModal.classList.add('active');
    });
    [btnNewTfClose, btnCancelTf].forEach(btn => {
        btn.addEventListener('click', () => {
            resetStorageMappings();
            tfModal.classList.remove('active');
        });
    });
}

// Form Handlers & Field Toggles
function setupForms() {
    // Login Form Submit
    const loginForm = document.getElementById('loginForm');
    if (loginForm) {
        loginForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const u = document.getElementById('loginUsername').value.trim();
            const p = document.getElementById('loginPassword').value;
            if (!u || !p) {
                const err = document.getElementById('loginError');
                if (err) {
                    err.textContent = getTranslation('login-error-empty');
                    err.classList.remove('hidden');
                }
                return;
            }
            await performLogin(u, p);
        });
    }

    // Logout Button
    const btnLogout = document.getElementById('btnLogout');
    if (btnLogout) {
        btnLogout.addEventListener('click', performLogout);
    }

    const epType = document.getElementById('endpointType');
    const vmwareFields = document.getElementById('vmwareFields');
    const olvmFields = document.getElementById('olvmFields');
    const hypervFields = document.getElementById('hypervFields');

    const proxmoxFields = document.getElementById('proxmoxFields');
    epType.addEventListener('change', () => {
        vmwareFields.classList.add('hidden');
        olvmFields.classList.add('hidden');
        hypervFields.classList.add('hidden');
        proxmoxFields.classList.add('hidden');

        if (epType.value === 'vmware_vsphere') {
            vmwareFields.classList.remove('hidden');
        } else if (epType.value === 'olvm') {
            olvmFields.classList.remove('hidden');
        } else if (epType.value === 'hyperv') {
            hypervFields.classList.remove('hidden');
        } else if (epType.value === 'proxmox') {
            proxmoxFields.classList.remove('hidden');
        }
    });

    // Submit Endpoint Form
    document.getElementById('endpointForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        const type = epType.value;
        const name = document.getElementById('endpointName').value;
        let connectionInfo = {};

        if (type === 'vmware_vsphere') {
            connectionInfo = {
                host: document.getElementById('vmwareHost').value,
                username: document.getElementById('vmwareUser').value,
                password: document.getElementById('vmwarePass').value,
                allow_untrusted: document.getElementById('vmwareUntrusted').checked
            };
        } else if (type === 'olvm') {
            connectionInfo = {
                url: document.getElementById('olvmUrl').value,
                username: document.getElementById('olvmUser').value,
                password: document.getElementById('olvmPass').value,
                insecure: document.getElementById('olvmInsecure').checked
            };
        } else if (type === 'hyperv') {
            connectionInfo = {
                host: document.getElementById('hypervHost').value,
                port: parseInt(document.getElementById('hypervPort').value),
                username: document.getElementById('hypervUser').value,
                password: document.getElementById('hypervPass').value,
                https: document.getElementById('hypervHttps').checked,
                cert_validation: document.getElementById('hypervInsecure').checked ? 'ignore' : 'validate',
                transport: document.getElementById('hypervTransport').value
            };
        } else if (type === 'proxmox') {
            connectionInfo = {
                url: document.getElementById('proxmoxUrl').value,
                username: document.getElementById('proxmoxUser').value,
                password: document.getElementById('proxmoxPass').value,
                insecure: document.getElementById('proxmoxInsecure').checked
            };
        }

        let url = `${API_BASE}/endpoints`;
        let method = 'POST';
        let successMsg = getTranslation('alert-ep-success');
        let errorMsg = getTranslation('alert-error-ep');
        let bodyPayload = {
            endpoint: {
                name,
                type,
                description: getTranslation('ep-created-via-dashboard'),
                connection_info: connectionInfo
            }
        };

        if (editingEndpointId) {
            url = `${API_BASE}/endpoints/${editingEndpointId}`;
            method = 'PUT';
            successMsg = getTranslation('alert-ep-update-success');
            errorMsg = getTranslation('alert-error-ep-update');
            bodyPayload = {
                endpoint: {
                    name,
                    connection_info: connectionInfo
                }
            };
        }

        try {
            const res = await fetchWithAuth(url, {
                method: method,
                headers: {
                    'Content-Type': 'application/json',
                    'X-Project-Id': 'admin'
                },
                body: JSON.stringify(bodyPayload)
            });

            if (!res.ok) throw new Error(await res.text());

            alert(successMsg);
            document.getElementById('endpointModal').classList.remove('active');
            resetEndpointModal();
            refreshAllData();
        } catch (err) {
            console.error(err);
            alert(`${errorMsg}: ${err.message}`);
        }
    });

    // Submit Transfer Form
    document.getElementById('transferForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const origin_endpoint_id = document.getElementById('transferSource').value;
    const destination_endpoint_id = document.getElementById('transferDest').value;
    const vmName = document.getElementById('transferVMs').value.trim();
    
    const sourceNet = document.getElementById('sourceNet').value.trim();
    const destNet = document.getElementById('destNet').value.trim();

    const network_map = {};
    if (sourceNet && destNet) {
        network_map[sourceNet] = destNet;
    }

    let storage_mappings = {};
    const backend_mappings = [];
    let defaultDestDomain = '';
    const olvmStorageInput = document.getElementById('transferStorageDomain');
    const proxmoxStorageInput = document.getElementById('transferProxmoxStorage');
    const vmwareDatastoreInput = document.getElementById('transferDatastore');

    if (olvmStorageInput && olvmStorageInput.value) {
        defaultDestDomain = olvmStorageInput.value.trim();
    } else if (proxmoxStorageInput && proxmoxStorageInput.value) {
        defaultDestDomain = proxmoxStorageInput.value.trim();
    } else if (vmwareDatastoreInput && vmwareDatastoreInput.value) {
        defaultDestDomain = vmwareDatastoreInput.value.trim();
    }

    document.querySelectorAll('.storage-mapping-row').forEach(row => {
        const srcInput = row.querySelector('.source-store');
        const destInput = row.querySelector('.dest-store');
        if (srcInput && destInput) {
            const src = srcInput.value.trim();
            let dest = destInput.value.trim();
            if (!dest) {
                dest = defaultDestDomain;
            }
            if (src && dest) {
                backend_mappings.push({
                    source: src,
                    destination: dest
                });
            }
        }
    });
    if (backend_mappings.length > 0) {
        storage_mappings = {
            backend_mappings
        };
    }

    try {
        // Get destination endpoint to determine type
        const endpoints = await fetchList('endpoints');
        const destEndpoint = endpoints.find(ep => ep.id === destination_endpoint_id);
        
        const preserve_mac_addresses = document.getElementById('transferPreserveMac').checked;
        let destination_environment = {};
        if (destEndpoint && destEndpoint.type === 'olvm') {
            destination_environment = {
                cluster_id: document.getElementById('transferCluster').value.trim(),
                storage_domain_id: document.getElementById('transferStorageDomain').value.trim(),
                preserve_mac_addresses
            };
        } else if (destEndpoint && destEndpoint.type === 'hyperv') {
            destination_environment = {
                default_switch: document.getElementById('transferSwitch').value.trim(),
                vm_path: document.getElementById('transferVmPath').value.trim(),
                vm_generation: document.getElementById('transferVmGeneration').value ? parseInt(document.getElementById('transferVmGeneration').value) : undefined,
                preserve_mac_addresses
            };
        } else if (destEndpoint && destEndpoint.type === 'proxmox') {
            destination_environment = {
                node: document.getElementById('transferProxmoxNode').value.trim(),
                storage: document.getElementById('transferProxmoxStorage').value.trim(),
                preserve_mac_addresses
            };
        } else if (destEndpoint && destEndpoint.type === 'vmware_vsphere') {
            destination_environment = {
                datacenter: document.getElementById('transferDatacenter').value.trim(),
                cluster: document.getElementById('transferClusterCompute').value.trim(),
                datastore: document.getElementById('transferDatastore').value.trim(),
                preserve_mac_addresses
            };
        }

        const res = await fetchWithAuth(`${API_BASE}/transfers`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Project-Id': 'admin'
            },
            body: JSON.stringify({
                transfer: {
                    origin_endpoint_id,
                    destination_endpoint_id,
                    source_environment: {},
                    destination_environment,
                    instances: [vmName],
                    network_map,
                    storage_mappings
                }
            })
        });

        if (!res.ok) throw new Error(await res.text());

        alert(getTranslation('alert-tf-success'));
        document.getElementById('transferModal').classList.remove('active');
        document.getElementById('transferForm').reset();
        resetStorageMappings();
        refreshAllData();
    } catch (err) {
        console.error(err);
        alert(`${getTranslation('alert-error-tf')}: ${err.message}`);
    }
    });

    // Storage Mappings dynamic UI and event listeners
    document.getElementById('btnAddStorageMapping').addEventListener('click', () => {
        const container = document.getElementById('storageMappingsContainer');
        container.appendChild(createStorageMappingRow('', ''));
    });

    document.getElementById('transferVMs').addEventListener('change', updateStorageMappingsFromVM);
    document.getElementById('transferSource').addEventListener('change', updateStorageMappingsFromVM);

    document.getElementById('transferStorageDomain').addEventListener('input', () => {
        const targetDomain = document.getElementById('transferStorageDomain').value.trim();
        document.querySelectorAll('.storage-mapping-row').forEach(row => {
            const destInput = row.querySelector('.dest-store');
            if (destInput && !destInput.value.trim()) {
                destInput.placeholder = targetDomain || getTranslation('placeholder-dest-store') || 'z.B. data';
            }
        });
    });
}

function createStorageMappingRow(source = '', destination = '') {
    const row = document.createElement('div');
    row.className = 'mapping-inputs storage-mapping-row';
    row.style.marginBottom = '0.5rem';
    
    const sourceInput = document.createElement('input');
    sourceInput.type = 'text';
    sourceInput.className = 'source-store';
    sourceInput.placeholder = getTranslation('placeholder-source-store') || 'z.B. datastore1';
    sourceInput.value = source;
    
    const arrow = document.createElement('span');
    arrow.className = 'arrow';
    arrow.innerHTML = '&rarr;';
    
    const destInput = document.createElement('input');
    destInput.type = 'text';
    destInput.className = 'dest-store';
    destInput.placeholder = getTranslation('placeholder-dest-store') || 'z.B. data';
    destInput.value = destination;
    
    const removeBtn = document.createElement('button');
    removeBtn.type = 'button';
    removeBtn.className = 'btn-remove-mapping';
    removeBtn.innerHTML = '&times;';
    removeBtn.addEventListener('click', () => {
        row.remove();
        const container = document.getElementById('storageMappingsContainer');
        if (container.children.length === 0) {
            container.appendChild(createStorageMappingRow('', ''));
        }
    });
    
    row.appendChild(sourceInput);
    row.appendChild(arrow);
    row.appendChild(destInput);
    row.appendChild(removeBtn);
    
    return row;
}

function resetStorageMappings() {
    const container = document.getElementById('storageMappingsContainer');
    container.innerHTML = '';
    container.appendChild(createStorageMappingRow('', ''));
}

async function fetchInstanceDetails(endpointId, instanceName) {
    const instanceId = btoa(unescape(encodeURIComponent(instanceName)))
        .replace(/\+/g, '-')
        .replace(/\//g, '_');
    const res = await fetchWithAuth(`${API_BASE}/endpoints/${endpointId}/instances/${instanceId}`, {
        headers: { 'X-Project-Id': 'admin' }
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    return data.instance;
}

async function updateStorageMappingsFromVM() {
    const sourceEndpointId = document.getElementById('transferSource').value;
    const vmName = document.getElementById('transferVMs').value.trim();
    
    if (!sourceEndpointId || !vmName) {
        return;
    }
    
    const container = document.getElementById('storageMappingsContainer');
    container.innerHTML = `<div class="loading-mappings" style="display: flex; align-items: center; gap: 0.5rem; color: var(--text-muted); font-size: 0.9rem;">
        <span class="spinner-small"></span>
        <span>${getTranslation('msg-loading') || 'Lade VM-Details...'}</span>
    </div>`;
    
    try {
        const instance = await fetchInstanceDetails(sourceEndpointId, vmName);
        if (instance && instance.devices && instance.devices.disks) {
            const datastores = new Set();
            instance.devices.disks.forEach(disk => {
                if (disk.storage_backend_identifier) {
                    datastores.add(disk.storage_backend_identifier);
                }
            });
            
            container.innerHTML = '';
            if (datastores.size > 0) {
                const targetDomain = document.getElementById('transferStorageDomain').value.trim();
                datastores.forEach(ds => {
                    container.appendChild(createStorageMappingRow(ds, targetDomain));
                });
            } else {
                container.appendChild(createStorageMappingRow('', ''));
            }
        } else {
            resetStorageMappings();
        }
    } catch (err) {
        console.error("Failed to load VM details for storage mapping:", err);
        resetStorageMappings();
    }
}

// Get lists and refresh components
async function refreshAllData() {
    try {
        const endpoints = await fetchList('endpoints');
        registeredEndpoints = endpoints;
        lastEndpointsData = endpoints;
        const transfers = await fetchList('transfers');
        lastTransfersData = transfers;
        const services = await fetchList('services');

        updateDashboardStats(endpoints, transfers, services);
        renderEndpointsGrid(endpoints);
        renderTransfersTable(transfers, endpoints);
        renderServicesTable(services);
    } catch (err) {
        console.error("Error refreshing data:", err);
        setAPIStatus(false);
    }
}

async function fetchList(resource) {
    const resourceName = resource.split('?')[0];
    try {
        const res = await fetchWithAuth(`${API_BASE}/${resource}`, {
            headers: { 'X-Project-Id': 'admin' }
        });
        if (!res.ok) throw new Error();
        setAPIStatus(true);
        const data = await res.json();
        return data[resourceName] || [];
    } catch (err) {
        setAPIStatus(false);
        throw err;
    }
}

function setAPIStatus(online) {
    const indicator = document.querySelector('.status-indicator');
    if (online) {
        indicator.className = 'status-indicator online';
    } else {
        indicator.className = 'status-indicator offline';
    }
}

function updateDashboardStats(endpoints, transfers, services) {
    document.getElementById('countEndpoints').textContent = endpoints.length;
    document.getElementById('countTransfers').textContent = transfers.length;

    // Check if any service has status other than UP
    const allUp = services.every(s => s.status === 'UP');
    const workerStatus = document.getElementById('workerStatus');
    if (services.length === 0) {
        workerStatus.textContent = getTranslation('status-no-services');
        workerStatus.style.color = "var(--text-muted)";
    } else if (allUp) {
        workerStatus.textContent = getTranslation('status-healthy');
        workerStatus.style.color = "var(--status-online)";
    } else {
        workerStatus.textContent = getTranslation('status-warning');
        workerStatus.style.color = "var(--status-warning)";
    }
}

// Render Endpoints List
function renderEndpointsGrid(endpoints) {
    const grid = document.getElementById('endpointsGrid');
    if (endpoints.length === 0) {
        grid.innerHTML = `<div class="stat-card" style="grid-column: 1/-1; justify-content: center;"><p class="text-muted">${getTranslation('msg-no-endpoints')}</p></div>`;
        return;
    }

     grid.innerHTML = endpoints.map(ep => {
        let typeBadge = `<span class="badge badge-olvm">${getTranslation('badge-olvm')}</span>`;
        if (ep.type === 'vmware_vsphere') {
            typeBadge = `<span class="badge badge-vmware">${getTranslation('badge-vmware')}</span>`;
        } else if (ep.type === 'hyperv') {
            typeBadge = `<span class="badge badge-hyperv">${getTranslation('badge-hyperv')}</span>`;
        } else if (ep.type === 'proxmox') {
            typeBadge = `<span class="badge badge-proxmox">${getTranslation('badge-proxmox')}</span>`;
        }

        let detailsHtml = '';
        if (ep.type === 'vmware_vsphere') {
            detailsHtml = `<p><span>vCenter:</span> ${ep.connection_info.host}</p><p><span>${getTranslation('label-username')}:</span> ${ep.connection_info.username}</p>`;
        } else if (ep.type === 'hyperv') {
            detailsHtml = `<p><span>Hyper-V:</span> ${ep.connection_info.host}:${ep.connection_info.port}</p><p><span>${getTranslation('label-username')}:</span> ${ep.connection_info.username}</p>`;
        } else if (ep.type === 'olvm') {
            detailsHtml = `<p><span>Engine:</span> ${ep.connection_info.url}</p><p><span>${getTranslation('label-username')}:</span> ${ep.connection_info.username}</p>`;
        } else if (ep.type === 'proxmox') {
            detailsHtml = `<p><span>Proxmox API:</span> ${ep.connection_info.url}</p><p><span>${getTranslation('label-username')}:</span> ${ep.connection_info.username}</p>`;
        }

        const storedUser = getStoredUser();
        const roles = (storedUser && storedUser.roles) || ['viewer'];
        const isAdmin = roles.includes('admin');
        const isOperator = roles.includes('operator') || isAdmin;
        const isViewerOnly = !isOperator;

        return `
            <div class="endpoint-card">
                <div class="endpoint-header">
                    <div class="endpoint-title">
                        <h3>${escapeHtml(ep.name)}</h3>
                        <p class="endpoint-desc">${escapeHtml(ep.description || '')}</p>
                    </div>
                    ${typeBadge}
                </div>
                <div class="endpoint-details">
                    ${detailsHtml}
                </div>
                <div class="endpoint-actions">
                    <button class="btn btn-primary" onclick="editEndpoint('${ep.id}')" style="margin-right: 8px;" ${isViewerOnly ? 'disabled title="' + getTranslation('role-viewer-notice') + '"' : ''}>${getTranslation('btn-edit')}</button>
                    <button class="btn btn-danger" onclick="deleteEndpoint('${ep.id}')" ${!isAdmin ? 'disabled title="Nur für Administratoren"' : ''}>${getTranslation('btn-delete')}</button>
                </div>
            </div>
        `;
    }).join('');
}

// Render Transfers
function renderTransfersTable(transfers, endpoints) {
    const tableBody = document.querySelector('#transfersTable tbody');
    const recentTableBody = document.querySelector('#recentTransfersTable tbody');

    const renderRows = (list) => {
        if (list.length === 0) {
            return `<tr><td colspan="6" class="text-center text-muted">${getTranslation('msg-no-transfers')}</td></tr>`;
        }

        return list.map(tf => {
            const sourceEp = endpoints.find(e => e.id === tf.origin_endpoint_id);
            const destEp = endpoints.find(e => e.id === tf.destination_endpoint_id);
            const sourceName = sourceEp ? sourceEp.name : getTranslation('status-unknown');
            const destName = destEp ? destEp.name : getTranslation('status-unknown');
            const status = tf.status || tf.last_execution_status || 'PENDING';
            let statusStyleClass = status.toLowerCase();
            if (statusStyleClass === 'unexecuted') {
                statusStyleClass = 'pending';
            }
            const statusClass = `status-${statusStyleClass}`;

            const isExpanded = expandedTransferIds.includes(tf.id);
            const caret = isExpanded ? '▼' : '▶';
            const toggleHtml = `
                <button class="btn-toggle-details" onclick="toggleTransferDetails('${tf.id}')" style="background:none; border:none; color:var(--accent-cyan); cursor:pointer; margin-right:6px; font-size:0.85rem; padding:0; outline:none;">
                    ${caret}
                </button>
            `;

            const storedUser = getStoredUser();
            const roles = (storedUser && storedUser.roles) || ['viewer'];
            const isAdmin = roles.includes('admin');
            const isOperator = roles.includes('operator') || isAdmin;
            const isViewerOnly = !isOperator;

            let actionsHtml = '';
            if (status === 'RUNNING' || status === 'CANCELLING') {
                actionsHtml = `<span class="text-muted">${getTranslation('msg-action-running')}</span>`;
            } else {
                actionsHtml = `
                    <div class="action-buttons">
                        <button class="btn btn-success" onclick="executeTransfer('${tf.id}')" ${isViewerOnly ? 'disabled title="' + getTranslation('role-viewer-notice') + '"' : ''}>${getTranslation('btn-replication')}</button>
                        <button class="btn btn-primary" onclick="deployTransfer('${tf.id}')" ${isViewerOnly ? 'disabled title="' + getTranslation('role-viewer-notice') + '"' : ''}>${getTranslation('btn-cutover')}</button>
                        <button class="btn btn-danger" onclick="deleteTransfer('${tf.id}')" ${!isAdmin ? 'disabled title="Nur für Administratoren"' : ''}>${getTranslation('btn-delete')}</button>
                    </div>
                `;
            }

            let detailsRowHtml = '';
            if (isExpanded) {
                const execution = tf.executions && tf.executions.length > 0 ? tf.executions[tf.executions.length - 1] : null;
                let executionContent = '';
                if (!execution) {
                    executionContent = `<p class="text-muted" style="padding:1rem;">${getTranslation('msg-no-execution')}</p>`;
                } else {
                    const tasks = execution.tasks || [];
                    const tasksList = tasks.map(task => {
                        let badgeClass = 'status-pending';
                        if (task.status === 'COMPLETED') badgeClass = 'status-completed';
                        else if (task.status === 'RUNNING') badgeClass = 'status-running';
                        else if (task.status === 'FAILED') badgeClass = 'status-failed';
                        
                        let excDetails = '';
                        if (task.exception_details) {
                            excDetails = `
                                <div class="task-exception-info">
                                    <code>${escapeHtml(JSON.stringify(task.exception_details))}</code>
                                </div>
                            `;
                        }
                        
                        return `
                            <div class="task-step-item">
                                <div class="task-step-header">
                                    <span class="badge ${badgeClass}">${task.status}</span>
                                    <span class="task-step-name">${escapeHtml(task.task_type)}</span>
                                    <span class="task-step-time">${task.updated_at ? new Date(task.updated_at + 'Z').toLocaleString() : ''}</span>
                                </div>
                                ${excDetails}
                            </div>
                        `;
                    }).join('');
                    executionContent = `
                        <div class="execution-details-expanded-box">
                            <h4 style="margin-bottom:0.75rem; font-size:0.95rem; font-weight:600;">${getTranslation('title-execution')} #${execution.number} (ID: <code>${execution.id}</code>)</h4>
                            <div class="tasks-steps-list">${tasksList}</div>
                        </div>
                    `;
                }
                detailsRowHtml = `
                    <tr class="transfer-details-row">
                        <td colspan="6">
                            <div class="transfer-details-wrapper">
                                ${executionContent}
                            </div>
                        </td>
                    </tr>
                `;
            }

            return `
                <tr>
                    <td>${toggleHtml}<code>${tf.id.substring(0, 8)}...</code></td>
                    <td><strong>${escapeHtml((tf.instances || []).join(', '))}</strong></td>
                    <td>${escapeHtml(sourceName)}</td>
                    <td>${escapeHtml(destName)}</td>
                    <td><span class="badge badge-status ${statusClass}">${status}</span></td>
                    <td>${actionsHtml}</td>
                </tr>
                ${detailsRowHtml}
            `;
        }).join('');
    };

    const rowsHtml = renderRows(transfers);
    tableBody.innerHTML = rowsHtml;
    recentTableBody.innerHTML = rowsHtml;
}

function toggleTransferDetails(id) {
    const idx = expandedTransferIds.indexOf(id);
    if (idx > -1) {
        expandedTransferIds.splice(idx, 1);
    } else {
        expandedTransferIds.push(id);
    }
    renderTransfersTable(lastTransfersData, lastEndpointsData);
}
window.toggleTransferDetails = toggleTransferDetails;

// Render Coriolis Services
function renderServicesTable(services) {
    const tableBody = document.querySelector('#servicesTable tbody');
    if (services.length === 0) {
        tableBody.innerHTML = `<tr><td colspan="5" class="text-center text-muted">${getTranslation('msg-no-services')}</td></tr>`;
        return;
    }

    tableBody.innerHTML = services.map(s => {
        const isUp = s.status === 'UP';
        const statusBadge = isUp ? 
            `<span class="badge status-completed">${getTranslation('status-up')}</span>` : 
            `<span class="badge status-failed">${getTranslation('status-down')}</span>`;
        
        const storedUser = getStoredUser();
        const isAdmin = storedUser && storedUser.roles && storedUser.roles.includes('admin');
        let actionBtn = '';
        if (!isUp) {
            actionBtn = `<button class="btn btn-danger btn-sm" onclick="deleteService('${s.id}')" ${!isAdmin ? 'disabled title="Nur für Administratoren"' : ''}>${getTranslation('btn-clean')}</button>`;
        }

        return `
            <tr>
                <td><strong>${escapeHtml(s.binary)}</strong></td>
                <td><code>${escapeHtml(s.host)}</code></td>
                <td>${statusBadge}</td>
                <td>${s.created_at ? new Date(s.created_at + 'Z').toLocaleString() : '-'}</td>
                <td>${actionBtn}</td>
            </tr>
        `;
    }).join('');
}

// Delete functions
async function deleteEndpoint(id) {
    if (!confirm(getTranslation('confirm-delete-ep'))) return;
    try {
        const res = await fetchWithAuth(`${API_BASE}/endpoints/${id}`, {
            method: 'DELETE',
            headers: { 'X-Project-Id': 'admin' }
        });
        if (!res.ok) throw new Error(await res.text());
        refreshAllData();
    } catch (err) {
        alert(`${getTranslation('alert-error-delete')}: ${err.message}`);
    }
}

async function deleteTransfer(id) {
    if (!confirm(getTranslation('confirm-delete-tf'))) return;
    try {
        const res = await fetchWithAuth(`${API_BASE}/transfers/${id}`, {
            method: 'DELETE',
            headers: { 'X-Project-Id': 'admin' }
        });
        if (!res.ok) throw new Error(await res.text());
        refreshAllData();
    } catch (err) {
        alert(`${getTranslation('alert-error-delete')}: ${err.message}`);
    }
}

async function deleteService(id) {
    if (!confirm(getTranslation('confirm-delete-service'))) return;
    try {
        const res = await fetchWithAuth(`${API_BASE}/services/${id}`, {
            method: 'DELETE',
            headers: { 'X-Project-Id': 'admin' }
        });
        if (!res.ok) throw new Error(await res.text());
        refreshAllData();
    } catch (err) {
        alert(`${getTranslation('alert-error-service')}: ${err.message}`);
    }
}

// Action Trigger
async function executeTransfer(id) {
    try {
        const res = await fetchWithAuth(`${API_BASE}/transfers/${id}/executions`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Project-Id': 'admin'
            },
            body: JSON.stringify({
                execution: {
                    shutdown_instances: false,
                    auto_deploy: false
                }
            })
        });
        if (!res.ok) throw new Error(await res.text());
        alert(getTranslation('alert-repl-success'));
        refreshAllData();
    } catch (err) {
        alert(`${getTranslation('alert-error-repl')}: ${err.message}`);
    }
}

async function deployTransfer(id) {
    if (!confirm(getTranslation('confirm-deploy'))) return;
    try {
        const res = await fetchWithAuth(`${API_BASE}/deployments`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Project-Id': 'admin'
            },
            body: JSON.stringify({
                deployment: {
                    transfer_id: id,
                    force: true
                }
            })
        });
        if (!res.ok) throw new Error(await res.text());
        alert(getTranslation('alert-deploy-success'));
        refreshAllData();
    } catch (err) {
        alert(`${getTranslation('alert-error-deploy')}: ${err.message}`);
    }
}

// Populate endpoint dropdowns for creation
async function loadEndpointsForSelect() {
    try {
        const endpoints = await fetchList('endpoints');
        const sourceSelect = document.getElementById('transferSource');
        const destSelect = document.getElementById('transferDest');

        const pleaseSelectText = getTranslation('select-please');
        sourceSelect.innerHTML = `<option value="">${pleaseSelectText}</option>`;
        destSelect.innerHTML = `<option value="">${pleaseSelectText}</option>`;

        endpoints.forEach(ep => {
            let typeLabel = ep.type;
            if (ep.type === 'vmware_vsphere') typeLabel = getTranslation('badge-vmware');
            else if (ep.type === 'olvm') typeLabel = getTranslation('badge-olvm');
            else if (ep.type === 'hyperv') typeLabel = getTranslation('badge-hyperv');
            else if (ep.type === 'proxmox') typeLabel = getTranslation('badge-proxmox');

            const opt = `<option value="${ep.id}">${escapeHtml(ep.name)} (${typeLabel})</option>`;
            if (ep.type === 'vmware_vsphere' || ep.type === 'olvm') {
                sourceSelect.innerHTML += opt;
            }
            if (ep.type === 'vmware_vsphere' || ep.type === 'olvm' || ep.type === 'hyperv' || ep.type === 'proxmox') {
                destSelect.innerHTML += opt;
            }
        });
        
        // Set up destination type change listener for field toggling
        destSelect.addEventListener('change', () => {
            const destEndpointId = destSelect.value;
            const tfOlvmFields = document.getElementById('tfOlvmFields');
            const tfHypervFields = document.getElementById('tfHypervFields');
            const tfProxmoxFields = document.getElementById('tfProxmoxFields');
            const tfVmwareFields = document.getElementById('tfVmwareFields');
            const tfStorageMapGroup = document.getElementById('tfStorageMapGroup');
            const destLabel = document.querySelector('#transferDest').previousElementSibling;
            
            tfOlvmFields.classList.add('hidden');
            tfHypervFields.classList.add('hidden');
            tfProxmoxFields.classList.add('hidden');
            tfVmwareFields.classList.add('hidden');
            tfStorageMapGroup.classList.remove('hidden');

            if (!destEndpointId) {
                if (destLabel) destLabel.textContent = getTranslation('label-tf-dest');
                return;
            }
            
            const destEndpoint = endpoints.find(ep => ep.id === destEndpointId);
            if (destEndpoint) {
                if (destEndpoint.type === 'olvm') {
                    tfOlvmFields.classList.remove('hidden');
                    if (destLabel) destLabel.textContent = getTranslation('label-tf-dest');
                } else if (destEndpoint.type === 'hyperv') {
                    tfHypervFields.classList.remove('hidden');
                    tfStorageMapGroup.classList.add('hidden');
                    if (destLabel) destLabel.textContent = getTranslation('label-tf-hyperv-dest');
                } else if (destEndpoint.type === 'proxmox') {
                    tfProxmoxFields.classList.remove('hidden');
                    if (destLabel) destLabel.textContent = "Ziel (Proxmox Endpunkt)";
                } else if (destEndpoint.type === 'vmware_vsphere') {
                    tfVmwareFields.classList.remove('hidden');
                    if (destLabel) destLabel.textContent = "Ziel (VMware Endpunkt)";
                }
            }
        });
    } catch (err) {
        console.error(err);
    }
}

// Escape strings to prevent XSS
function escapeHtml(str) {
    if (typeof str !== 'string') return '';
    return str
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

const FAQ_ITEMS = {
    de: [
        {
            q: "Welche Namenseinschränkungen gibt es für VMs in vCenter?",
            a: "VM-Namen müssen exakt mit dem Anzeigenamen (Inventory Name) im vCenter übereinstimmen. Die Groß-/Kleinschreibung muss beachtet werden. Sonderzeichen, die von vCenter unterstützt werden, sind generell zulässig, jedoch sollten Leerzeichen vermieden werden, um Probleme bei Migrationsskripten zu vermeiden."
        },
        {
            q: "Warum können Endpunkte mit aktiven Migrationen nicht gelöscht werden?",
            a: "Coriolis verhindert das Löschen von Endpunkten, die mit aktiven Replikations- oder Migrations-Jobs verknüpft sind, da dies verwaiste Jobs (orphaned transfers) hinterlassen würde (Fehler 403: '1 transfers would be orphaned!'). Um einen Endpunkt zu löschen, müssen zuerst alle verknüpften Migrations-Jobs gelöscht werden."
        },
        {
            q: "Was ist der Unterschied zwischen Replica (Replikation) und Cutover (Migration/Cutover)?",
            a: "<strong>Replica (Replikation):</strong> Führt eine inkrementelle Synchronisierung der VM-Disks von der Quelle zum Ziel durch, während die Quell-VM online bleibt. Dies kann beliebig oft wiederholt werden, um die Ausfallzeit zu minimieren.<br><strong>Cutover (Migration):</strong> Führt die finale Synchronisierung durch, fährt die Quell-VM herunter, trennt die Netzwerke und erstellt/registriert die VM auf der Zielplattform (OLVM), sodass sie dort einsatzbereit ist."
        },
        {
            q: "Wie ist die Konfigurationsdatei coriolis.conf aufgebaut und was bedeuten die einzelnen Sektionen?",
            a: "Die <code>coriolis.conf</code> ist die zentrale Konfigurationsdatei der Coriolis-Dienste. Hier sind die Hauptabschnitte:<br><br>" +
               "• <strong>[DEFAULT]</strong>: Enthält allgemeine Einstellungen. <code>debug</code> und <code>verbose</code> steuern die Logging-Tiefe. <code>transport_url</code> und <code>messaging_transport_url</code> definieren die Verbindungsdaten zum RabbitMQ-Message-Broker (wichtig für die Kommunikation der Dienste untereinander). <code>providers</code> listet die aktiven Treiber (z.B. VMware-Export und OLVM-Import).<br>" +
               "• <strong>[database]</strong>: Konfiguriert die Datenbankverbindung. <code>connection</code> spezifiziert die Verbindungs-URL zur MariaDB/MySQL-Datenbank (einschließlich Benutzername, Passwort und Hostname).<br>" +
               "• <strong>[api]</strong>: Bestimmt die REST-API-Schnittstelle. <code>api_migration_listen</code> und <code>api_migration_listen_port</code> steuern IP und Port (Standard: 7667) des API-Daemons. <code>api_migration_workers</code> definiert die Anzahl paralleler API-Prozesse.<br>" +
               "• <strong>[oslo_concurrency]</strong>: Regelt die prozessübergreifende Synchronisation. <code>lock_path</code> gibt das Verzeichnis für Sperrdateien an (muss für den Coriolis-Benutzer beschreibbar sein, z.B. <code>/tmp</code>)."
        }
    ],
    en: [
        {
            q: "What naming restrictions apply to VMs in vCenter?",
            a: "VM names must match the inventory display name in vCenter exactly, including case sensitivity. While special characters supported by vCenter are generally allowed, spaces should be avoided to prevent issues with downstream migration scripts."
        },
        {
            q: "Why can't endpoints with active migrations be deleted?",
            a: "Coriolis prevents deleting endpoints associated with active replication or migration jobs to prevent leaving orphaned tasks (403 error: '1 transfers would be orphaned!'). To delete an endpoint, you must delete all migration jobs referencing it first."
        },
        {
            q: "What is the difference between Replica (Replication) and Cutover (Migration/Cutover)?",
            a: "<strong>Replica (Replication):</strong> Performs incremental synchronization of VM disks from source to target while the source VM remains powered on. This can be run multiple times to minimize final sync time.<br><strong>Cutover (Migration):</strong> Performs the final sync, powers off the source VM, disconnects source networks, and boots/registers the VM on the target platform (OLVM) so it is ready for production."
        },
        {
            q: "How is the coriolis.conf configuration file structured and what do the individual sections mean?",
            a: "The <code>coriolis.conf</code> is the main configuration file for Coriolis services. Here is an overview of the primary sections:<br><br>" +
               "• <strong>[DEFAULT]</strong>: Contains global settings. <code>debug</code> and <code>verbose</code> control log verbosity. <code>transport_url</code> and <code>messaging_transport_url</code> define the connection strings to the RabbitMQ messaging broker (critical for inter-service communication). <code>providers</code> lists active migration drivers (e.g. VMware export and OLVM import).<br>" +
               "• <strong>[database]</strong>: Configures the database backend. <code>connection</code> specifies the connection URL to the MariaDB/MySQL database (including user, password, and hostname).<br>" +
               "• <strong>[api]</strong>: Defines API daemon options. <code>api_migration_listen</code> and <code>api_migration_listen_port</code> control the IP and port (default: 7667) the REST API listens on. <code>api_migration_workers</code> specifies the worker count.<br>" +
               "• <strong>[oslo_concurrency]</strong>: Manages lock synchronization. <code>lock_path</code> specifies the directory for process lock files (must be writeable by the Coriolis user, e.g. <code>/tmp</code>)."
        }
    ]
};

function renderFaq() {
    const faqList = document.getElementById('faqList');
    if (!faqList) return;

    const items = FAQ_ITEMS[currentLang] || FAQ_ITEMS.en;
    faqList.innerHTML = items.map((item, idx) => `
        <div class="faq-item">
            <div class="faq-question" onclick="toggleFaq(${idx})">
                <span class="faq-toggle-icon" id="faq-icon-${idx}">▶</span>
                <span>${escapeHtml(item.q)}</span>
            </div>
            <div class="faq-answer hidden" id="faq-answer-${idx}">
                <p>${item.a}</p>
            </div>
        </div>
    `).join('');
}

function toggleFaq(idx) {
    const answer = document.getElementById(`faq-answer-${idx}`);
    const icon = document.getElementById(`faq-icon-${idx}`);
    
    if (answer.classList.contains('hidden')) {
        answer.classList.remove('hidden');
        icon.classList.add('rotated');
    } else {
        answer.classList.add('hidden');
        icon.classList.remove('rotated');
    }
}

// Bind to window to allow inline onclick handlers to run
window.toggleFaq = toggleFaq;

function setupConfigEditor() {
    const select = document.getElementById('configSelect');
    const textarea = document.getElementById('configTextarea');
    const btnSave = document.getElementById('btnSaveConfig');

    if (!select || !textarea || !btnSave) return;

    // Fetch lists of configurations
    fetchConfigsList(select);

    select.addEventListener('change', async () => {
        const fileId = select.value;
        if (!fileId) {
            textarea.value = '';
            textarea.readOnly = true;
            btnSave.disabled = true;
            return;
        }

        const storedUser = getStoredUser();
        const isAdmin = storedUser && storedUser.roles && storedUser.roles.includes('admin');

        try {
            const res = await fetchWithAuth(`${API_BASE}/configs/${fileId}`, {
                headers: { 'X-Project-Id': 'admin' }
            });
            if (!res.ok) throw new Error(await res.text());
            const data = await res.json();
            textarea.value = data.config.content || '';
            textarea.readOnly = !isAdmin;
            btnSave.disabled = !isAdmin;
            if (!isAdmin) {
                btnSave.title = 'Nur für Administratoren';
            }
        } catch (err) {
            console.error(err);
            alert(`${getTranslation('alert-error-config-load')}: ${err.message}`);
            textarea.value = '';
            textarea.readOnly = true;
            btnSave.disabled = true;
        }
    });

    btnSave.addEventListener('click', async () => {
        const fileId = select.value;
        if (!fileId) return;

        btnSave.disabled = true;
        const originalText = btnSave.textContent;
        btnSave.textContent = getTranslation('msg-action-running');

        try {
            const res = await fetchWithAuth(`${API_BASE}/configs/${fileId}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Project-Id': 'admin'
                },
                body: JSON.stringify({
                    config: {
                        content: textarea.value
                    }
                })
            });

            if (!res.ok) throw new Error(await res.text());
            alert(getTranslation('alert-config-save-success'));
        } catch (err) {
            console.error(err);
            alert(`${getTranslation('alert-error-config-save')}: ${err.message}`);
        } finally {
            const storedUser = getStoredUser();
            const isAdmin = storedUser && storedUser.roles && storedUser.roles.includes('admin');
            btnSave.disabled = !isAdmin;
            btnSave.textContent = getTranslation('btn-save-config');
        }
    });
}

async function fetchConfigsList(selectEl) {
    if (!selectEl) {
        selectEl = document.getElementById('configSelect');
    }
    if (!selectEl) return;

    const defaultConfigs = [
        { id: 'coriolis.conf', name: 'coriolis.conf' },
        { id: 'api-paste.ini', name: 'api-paste.ini' },
        { id: 'policy.yaml', name: 'policy.yaml' },
        { id: 'users.yaml', name: 'users.yaml' }
    ];

    const currentVal = selectEl.value;
    const pleaseSelectText = getTranslation('select-please');

    let configsToRender = defaultConfigs;

    try {
        const res = await fetchWithAuth(`${API_BASE}/configs`, {
            headers: { 'X-Project-Id': 'admin' }
        });
        if (res.ok) {
            const data = await res.json();
            if (data.configs && data.configs.length > 0) {
                configsToRender = data.configs;
            }
        }
    } catch (err) {
        console.warn("Using default configs list:", err);
    }

    let html = `<option value="">${pleaseSelectText}</option>`;
    configsToRender.forEach(cfg => {
        html += `<option value="${cfg.id}">${cfg.name}</option>`;
    });
    selectEl.innerHTML = html;
    if (currentVal) {
        selectEl.value = currentVal;
    }
}

