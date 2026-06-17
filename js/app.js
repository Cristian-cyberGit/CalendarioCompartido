/**
 * LogiFamily Client Application Logic
 * Gestiona el enrutamiento de la SPA, interacción del calendario,
 * listas de compras y modales de validación avanzada de conflictos de concurrencia.
 */

// --- CONFIGURACIÓN E INSTANCIA DE ESTADO ---
const CONFIG = {
    // La API es relativa, permitiendo que funcione tanto con el servidor Python
    // (que intercepta las rutas .php) como con un servidor Apache/PHP estándar.
    apiAuth: 'api/auth.php',
    apiEvents: 'api/events.php',
    apiShopping: 'api/shopping.php',
    apiShifts: 'api/shifts.php'
};

const state = {
    user: null,    // { id, nombre, email }
    group: null,   // { id, nombre, codigo_acceso, rol }
    currentDate: new Date(),
    events: [],
    shifts: [],    // Lista de turnos del grupo
    selectedPaintShift: null, // Turno seleccionado para pintar rápidamente ('manana', 'tarde', 'noche', 'libre', 'borrar' o null)
    shoppingList: { id: null, name: '', items: [] },
    activeTab: 'calendar' // 'calendar' o 'shopping'
};

// Diccionario de festivos fijos y móviles de 2026 (Año de ejecución y datos semilla)
const HOLIDAYS_2026 = {
    "2026-01-01": "Año Nuevo",
    "2026-01-06": "Día de Reyes",
    "2026-03-23": "Día de San José",
    "2026-04-02": "Jueves Santo",
    "2026-04-03": "Viernes Santo",
    "2026-04-05": "Pascua de Resurrección",
    "2026-05-01": "Día del Trabajo",
    "2026-05-25": "Ascensión del Señor",
    "2026-06-15": "Corpus Christi",
    "2026-06-22": "Sagrado Corazón",
    "2026-06-29": "San Pedro y San Pablo",
    "2026-07-20": "Día de la Independencia",
    "2026-08-07": "Batalla de Boyacá",
    "2026-08-17": "Asunción de la Virgen",
    "2026-10-12": "Día de la Raza",
    "2026-11-02": "Todos los Santos",
    "2026-11-16": "Independencia de Cartagena",
    "2026-12-08": "Inmaculada Concepción",
    "2026-12-25": "Navidad"
};

// --- INICIALIZACIÓN ---
document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    checkAuthSession();
    registerEventListeners();
});

// --- ENRUTAMIENTO SPA Y ESTADO DE SESIÓN ---
function checkAuthSession() {
    const savedUser = localStorage.getItem('user');
    const savedGroup = localStorage.getItem('group');

    if (savedUser) {
        state.user = JSON.parse(savedUser);
        state.group = savedGroup ? JSON.parse(savedGroup) : null;
        updateUIForAuthenticatedUser();
    } else {
        showView('view-auth');
    }
}

function updateUIForAuthenticatedUser() {
    document.getElementById('user-display').textContent = `👋 ${state.user.nombre}`;
    document.getElementById('user-display').style.display = 'inline';
    document.getElementById('logout-btn').style.display = 'inline';

    if (!state.group) {
        showView('view-group-setup');
    } else {
        document.getElementById('app-tabs').style.display = 'flex';
        document.getElementById('active-group-title').textContent = state.group.nombre;
        document.getElementById('active-group-code').textContent = state.group.codigo_acceso;
        showView('view-main-app');
        loadAppData();
    }
}

function showView(viewId) {
    document.querySelectorAll('.view-route').forEach(view => {
        view.classList.remove('active');
    });
    const activeView = document.getElementById(viewId);
    if (activeView) activeView.classList.add('active');
}

function loadAppData() {
    if (state.activeTab === 'calendar') {
        loadEvents();
    } else if (state.activeTab === 'shopping') {
        loadShoppingList();
    }
}

// --- GESTIÓN DE TEMA (CLARO/OSCURO) ---
function initTheme() {
    const savedTheme = localStorage.getItem('theme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    
    if (savedTheme === 'dark' || (!savedTheme && prefersDark)) {
        document.body.classList.add('dark-theme');
    } else {
        document.body.classList.remove('dark-theme');
    }
}

function toggleTheme() {
    if (document.body.classList.contains('dark-theme')) {
        document.body.classList.remove('dark-theme');
        localStorage.setItem('theme', 'light');
    } else {
        document.body.classList.add('dark-theme');
        localStorage.setItem('theme', 'dark');
    }
}

// --- COMUNICACIÓN CON LA API (FETCH WRAPPERS) ---
async function apiFetch(url, options = {}) {
    const headers = options.headers || {};
    if (state.user) {
        headers['User-ID'] = state.user.id.toString();
    }
    
    options.headers = {
        'Content-Type': 'application/json',
        ...headers
    };

    try {
        const response = await fetch(url, options);
        // Manejar códigos de conflicto/error que devuelven JSON
        if (response.status === 401) {
            handleLogout();
            throw new Error("Sesión no autorizada o expirada");
        }
        
        const data = await response.json();
        if (!response.ok && response.status !== 409 && response.status !== 400) {
            throw new Error(data.error || 'Ocurrió un error en la solicitud.');
        }
        return { data, status: response.status };
    } catch (error) {
        showToast(error.message || 'Error de conexión con el servidor', 'error');
        throw error;
    }
}

// --- GESTIÓN DE EVENTOS (CALENDARIO) ---
async function loadEvents() {
    if (!state.group) return;
    try {
        const { data } = await apiFetch(`${CONFIG.apiEvents}?grupo_id=${state.group.id}`, { method: 'GET' });
        if (data.success) {
            state.events = data.events;
            await loadShifts(false); // Cargar turnos sin forzar re-renderizado
            renderCalendar();
            renderUpcomingEvents();
        } else {
            showToast(data.error, 'error');
        }
    } catch (e) {
        console.error("Error al cargar eventos", e);
    }
}

async function loadShifts(shouldRender = true) {
    if (!state.group) return;
    try {
        const { data } = await apiFetch(`${CONFIG.apiShifts}?grupo_id=${state.group.id}`, { method: 'GET' });
        if (data.success) {
            state.shifts = data.shifts;
            if (shouldRender) {
                renderCalendar();
            }
        }
    } catch (e) {
        console.error("Error al cargar turnos", e);
    }
}

function renderCalendar() {
    const grid = document.getElementById('calendar-grid');
    grid.innerHTML = '';
    
    const year = state.currentDate.getFullYear();
    const month = state.currentDate.getMonth();
    
    // Nombres de los días de la semana
    const days = ['Dom', 'Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb'];
    days.forEach(day => {
        const dayHeader = document.createElement('div');
        dayHeader.className = 'calendar-day-name';
        dayHeader.textContent = day;
        grid.appendChild(dayHeader);
    });

    // Título del mes y año
    const monthNames = [
        "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
    ];
    document.getElementById('calendar-month-year').textContent = `${monthNames[month]} ${year}`;

    // Primer día del mes
    const firstDayIndex = new Date(year, month, 1).getDay();
    // Último día del mes
    const lastDay = new Date(year, month + 1, 0).getDate();
    // Último día del mes anterior
    const prevLastDay = new Date(year, month, 0).getDate();

    // Rellenar días del mes anterior
    for (let x = firstDayIndex; x > 0; x--) {
        const cell = document.createElement('div');
        cell.className = 'calendar-day-cell other-month';
        const dayNum = prevLastDay - x + 1;
        cell.innerHTML = `<div class="cell-day-body"><span class="calendar-day-number">${dayNum}</span></div>`;
        grid.appendChild(cell);
    }

    // Días del mes actual
    const today = new Date();
    for (let i = 1; i <= lastDay; i++) {
        const cell = document.createElement('div');
        cell.className = 'calendar-day-cell';
        
        if (i === today.getDate() && month === today.getMonth() && year === today.getFullYear()) {
            cell.classList.add('today');
        }
        
        const cellDateString = `${year}-${String(month + 1).padStart(2, '0')}-${String(i).padStart(2, '0')}`;
        
        // Determinar si es domingo o día festivo en 2026
        const cellDate = new Date(year, month, i);
        const isSunday = cellDate.getDay() === 0;
        const holidayName = HOLIDAYS_2026[cellDateString];
        
        if (isSunday || holidayName) {
            cell.classList.add('holiday');
        }
        
        // Crear contenedor para el cuerpo del día
        const cellBody = document.createElement('div');
        cellBody.className = 'cell-day-body';
        
        // Añadir el número del día al cuerpo
        const numSpan = document.createElement('span');
        numSpan.className = 'calendar-day-number';
        numSpan.textContent = i;
        cellBody.appendChild(numSpan);
        
        // Si es festivo con nombre, renderizar una etiqueta sutil
        if (holidayName) {
            const hLabel = document.createElement('span');
            hLabel.className = 'holiday-label';
            hLabel.textContent = holidayName;
            hLabel.title = holidayName;
            cellBody.appendChild(hLabel);
        }
        
        // Filtrar y renderizar turnos para este día (Banner superior 1/4 del día)
        const dayShifts = state.shifts.filter(s => s.fecha === cellDateString);
        if (dayShifts.length > 0) {
            const shiftsHeader = document.createElement('div');
            shiftsHeader.className = 'cell-shifts-header';
            
            dayShifts.forEach(shift => {
                const block = document.createElement('div');
                block.className = `cell-shift-block shift-color-${shift.tipo}`;
                
                let label = 'Mañana';
                if (shift.tipo === 'tarde') label = 'Tarde';
                else if (shift.tipo === 'noche') label = 'Noche';
                else if (shift.tipo === 'libre') label = 'Libre';
                
                const nameShort = shift.usuario_nombre.split(' ')[0];
                block.textContent = nameShort;
                block.title = `${label} - ${shift.usuario_nombre}`;
                shiftsHeader.appendChild(block);
            });
            
            cell.appendChild(shiftsHeader);
        }
        
        cell.appendChild(cellBody);
        
        // Filtrar y renderizar eventos para este día
        const dayEvents = state.events.filter(e => {
            const evStartDate = e.fecha_inicio.split(' ')[0]; // YYYY-MM-DD
            return evStartDate === cellDateString;
        });

        dayEvents.forEach(event => {
            const tag = document.createElement('div');
            tag.className = `calendar-event-tag event-cat-${event.categoria || 'general'}`;
            tag.textContent = event.titulo;
            tag.title = `${event.titulo} (${event.fecha_inicio.split(' ')[1]} - ${event.fecha_fin.split(' ')[1]})`;
            tag.addEventListener('click', (e) => {
                e.stopPropagation();
                if (state.selectedPaintShift) {
                    // Si el pintor de turnos está activo, hacer click pinta el día completo
                    paintShift(cellDateString, state.selectedPaintShift);
                } else {
                    openEventModal(event);
                }
            });
            cellBody.appendChild(tag);
        });

        // Permitir hacer clic en la celda
        cell.addEventListener('click', () => {
            if (state.selectedPaintShift) {
                paintShift(cellDateString, state.selectedPaintShift);
            } else {
                const startStr = `${cellDateString}T09:00`;
                const endStr = `${cellDateString}T10:00`;
                openEventModal({ fecha_inicio: startStr, fecha_fin: endStr });
            }
        });

        grid.appendChild(cell);
    }

    // Rellenar días del mes siguiente para cuadrar la grilla (múltiplo de 7)
    const totalCells = grid.children.length - 7; // descontar cabeceras
    const remainingCells = 42 - totalCells; // Grilla de 6 semanas fija
    for (let j = 1; j <= remainingCells; j++) {
        const cell = document.createElement('div');
        cell.className = 'calendar-day-cell other-month';
        cell.innerHTML = `<div class="cell-day-body"><span class="calendar-day-number">${j}</span></div>`;
        grid.appendChild(cell);
    }
}

async function paintShift(fecha, tipo) {
    if (!state.group || !state.user) return;
    
    // Clonación del estado actual por si falla la API
    const previousShifts = JSON.parse(JSON.stringify(state.shifts));
    
    // Búsqueda del turno asignado previamente por este usuario en esta fecha
    const existingIndex = state.shifts.findIndex(s => s.fecha === fecha && s.usuario_id === state.user.id);
    
    if (tipo === 'borrar') {
        if (existingIndex > -1) {
            state.shifts.splice(existingIndex, 1);
        }
    } else {
        const newShift = {
            grupo_id: state.group.id,
            usuario_id: state.user.id,
            fecha: fecha,
            tipo: tipo,
            usuario_nombre: state.user.nombre
        };
        if (existingIndex > -1) {
            state.shifts[existingIndex] = newShift;
        } else {
            state.shifts.push(newShift);
        }
    }
    
    // Renderizado óptimo inmediato en frontend para respuesta táctil instantánea
    renderCalendar();
    
    try {
        const { data } = await apiFetch(`${CONFIG.apiShifts}?action=set`, {
            method: 'POST',
            body: JSON.stringify({
                grupo_id: state.group.id,
                fecha: fecha,
                tipo: tipo
            })
        });
        
        if (!data.success) {
            // Revertir cambios en caso de error en el backend
            state.shifts = previousShifts;
            renderCalendar();
            showToast(data.error || 'No se pudo guardar el turno.', 'error');
        }
    } catch (e) {
        state.shifts = previousShifts;
        renderCalendar();
        console.error("Error guardando turno", e);
    }
}

function renderUpcomingEvents() {
    const listContainer = document.getElementById('upcoming-list');
    listContainer.innerHTML = '';
    
    // Obtener los siguientes 5 eventos desde hoy
    const now = new Date();
    const upcoming = state.events.filter(e => {
        const evStart = new Date(e.fecha_inicio.replace(' ', 'T'));
        return evStart >= now;
    }).slice(0, 5);

    if (upcoming.length === 0) {
        listContainer.innerHTML = '<p class="text-muted" style="font-size: 0.9rem;">No hay actividades programadas.</p>';
        return;
    }

    upcoming.forEach(e => {
        const item = document.createElement('div');
        item.className = 'upcoming-event-item';
        item.style.borderLeftColor = `var(--cat-${e.categoria || 'general'})`;
        
        // Formatear fecha legible
        const evDate = new Date(e.fecha_inicio.replace(' ', 'T'));
        const dateFormatted = evDate.toLocaleDateString('es-ES', { weekday: 'short', day: 'numeric', month: 'short' });
        const timeFormatted = e.fecha_inicio.split(' ')[1].substring(0, 5);

        item.innerHTML = `
            <div class="upcoming-event-title">${e.titulo}</div>
            <div class="upcoming-event-time">📅 ${dateFormatted} a las ${timeFormatted} (${e.creador_nombre || 'Familiar'})</div>
        `;
        item.addEventListener('click', () => openEventModal(e));
        listContainer.appendChild(item);
    });
}

// --- MANEJO DE MODAL DE EVENTO CON RESOLUCIÓN DE CONFLICTOS ---
function openEventModal(event = null) {
    const modal = document.getElementById('modal-event');
    const alertContainer = document.getElementById('event-alert-container');
    alertContainer.innerHTML = ''; // Limpiar alertas previas
    
    // Resetear formulario
    document.getElementById('form-event').reset();
    
    if (event && event.id) {
        // Modo Edición
        document.getElementById('event-modal-title').textContent = 'Editar Actividad';
        document.getElementById('event-id').value = event.id;
        document.getElementById('event-version').value = event.version || 1;
        document.getElementById('event-title').value = event.titulo;
        document.getElementById('event-desc').value = event.descripcion || '';
        document.getElementById('event-cat').value = event.categoria || 'general';
        
        // SQLite/MySQL usan espacios en sus strings "YYYY-MM-DD HH:MM:SS".
        // input[type=datetime-local] requiere "YYYY-MM-DDTHH:MM"
        const startIso = event.fecha_inicio.replace(' ', 'T').substring(0, 16);
        const endIso = event.fecha_fin.replace(' ', 'T').substring(0, 16);
        document.getElementById('event-start').value = startIso;
        document.getElementById('event-end').value = endIso;
        
        document.getElementById('event-delete-btn').style.display = 'inline-block';
    } else {
        // Modo Creación
        document.getElementById('event-modal-title').textContent = 'Registrar Nueva Actividad';
        document.getElementById('event-id').value = '';
        document.getElementById('event-version').value = '1';
        document.getElementById('event-delete-btn').style.display = 'none';
        
        if (event && event.fecha_inicio) {
            document.getElementById('event-start').value = event.fecha_inicio.substring(0, 16);
            document.getElementById('event-end').value = event.fecha_fin.substring(0, 16);
        }
    }
    
    modal.classList.add('active');
}

function closeEventModal() {
    document.getElementById('modal-event').classList.remove('active');
}

async function saveEvent(event, force = false) {
    const eventId = document.getElementById('event-id').value;
    const url = `${CONFIG.apiEvents}?action=${eventId ? 'update' : 'create'}`;
    
    const payload = {
        grupo_id: state.group.id,
        titulo: document.getElementById('event-title').value,
        descripcion: document.getElementById('event-desc').value,
        categoria: document.getElementById('event-cat').value,
        // Enviar en formato MySQL/SQLite: "YYYY-MM-DD HH:MM:SS"
        fecha_inicio: document.getElementById('event-start').value.replace('T', ' ') + ':00',
        fecha_fin: document.getElementById('event-end').value.replace('T', ' ') + ':00',
        force: force
    };

    if (eventId) {
        payload.id = parseInt(eventId);
        payload.version = parseInt(document.getElementById('event-version').value);
    }

    try {
        const { data, status } = await apiFetch(url, {
            method: 'POST',
            body: JSON.stringify(payload)
        });

        // 1. Manejo de Conflictos Absolutos (409 Conflict o campo conflict = true)
        if (status === 409 || data.conflict) {
            showConflictAlert(data.details);
            return;
        }

        // 2. Manejo de Advertencias de Proximidad (200 con warning = true)
        if (data.warning) {
            showProximityWarning(data.details, () => {
                // Si el usuario acepta proceder a pesar de la advertencia, forzamos
                saveEvent(event, true);
            });
            return;
        }

        // 3. Manejo de Errores de Concurrencia (Optimistic Lock)
        if (data.concurrency_error) {
            showToast(data.error, 'error');
            closeEventModal();
            loadEvents();
            return;
        }

        if (data.success) {
            showToast(eventId ? 'Actividad actualizada.' : 'Actividad registrada.', 'success');
            closeEventModal();
            loadEvents();
        } else {
            showToast(data.error || 'Error al guardar.', 'error');
        }

    } catch (e) {
        console.error("Error guardando evento", e);
    }
}

// Muestra el panel con sugerencias del validador de Python en el modal
function showConflictAlert(details) {
    const alertContainer = document.getElementById('event-alert-container');
    let conflictingTitles = details.conflicting_events.map(e => `"${e.title}"`).join(', ');
    
    let html = `
        <div class="alert-box alert-box-danger">
            <strong>⚠️ Conflicto de Horario detectado</strong>
            <div>Esta hora choca directamente con: ${conflictingTitles}.</div>
    `;

    if (details.suggestions && details.suggestions.length > 0) {
        html += `
            <div style="margin-top: 0.5rem; font-weight: 600;">Sugerencias de Horarios Libres:</div>
            <ul class="suggestions-list">
        `;
        details.suggestions.forEach(sug => {
            // Convertir fechas YYYY-MM-DD HH:MM:SS a formato legible e ISO para imputar en el formulario
            const displayStart = sug.start.substring(11, 16);
            const displayEnd = sug.end.substring(11, 16);
            const dateStr = sug.start.substring(0, 10);
            
            const startIso = sug.start.replace(' ', 'T').substring(0, 16);
            const endIso = sug.end.replace(' ', 'T').substring(0, 16);
            
            html += `
                <li class="suggestion-item" onclick="applySuggestedTime('${startIso}', '${endIso}')">
                    💡 ${dateStr} de ${displayStart} a ${displayEnd} <br>
                    <small style="color: var(--text-muted)">(${sug.reason})</small>
                </li>
            `;
        });
        html += '</ul>';
    } else {
        html += `<div>Prueba con otra fecha u hora para continuar.</div>`;
    }

    html += `</div>`;
    alertContainer.innerHTML = html;
}

// Aplica la sugerencia del validador directamente a los inputs
window.applySuggestedTime = function(startIso, endIso) {
    document.getElementById('event-start').value = startIso;
    document.getElementById('event-end').value = endIso;
    // Limpiar la alerta para que intente guardar de nuevo
    document.getElementById('event-alert-container').innerHTML = '';
    showToast("Horario sugerido aplicado. ¡Listo para guardar!", "success");
};

// Muestra advertencia de proximidad (evento a menos de 15 minutos de otro)
function showProximityWarning(details, onProceed) {
    const bodyText = `
        <p>El validador detectó que esta actividad está muy cercana a otra:</p>
        <ul style="margin: 1rem 0; padding-left: 1.5rem;">
            ${details.warnings.map(w => `<li><strong>${w.title}</strong>: ${w.message}</li>`).join('')}
        </ul>
        <p>¿Quieres registrarla de todas formas?</p>
    `;
    
    openConfirmModal("Advertencia de Proximidad", bodyText, onProceed);
}

// --- GESTIÓN DE LISTA DE COMPRAS (INTEGRACIÓN DIFUSA) ---
async function loadShoppingList() {
    if (!state.group) return;
    try {
        const { data } = await apiFetch(`${CONFIG.apiShopping}?grupo_id=${state.group.id}`, { method: 'GET' });
        if (data.success) {
            state.shoppingList.id = data.list_id;
            state.shoppingList.name = data.list_name;
            state.shoppingList.items = data.items;
            renderShoppingItems();
        } else {
            showToast(data.error, 'error');
        }
    } catch (e) {
        console.error("Error al cargar compras", e);
    }
}

function renderShoppingItems() {
    const container = document.getElementById('shopping-items-container');
    container.innerHTML = '';

    if (state.shoppingList.items.length === 0) {
        container.innerHTML = `
            <div style="text-align: center; padding: 2rem; color: var(--text-muted)">
                🛒 ¡La lista está vacía! Añade insumos para centralizar las compras familiares.
            </div>
        `;
        return;
    }

    state.shoppingList.items.forEach(item => {
        const div = document.createElement('div');
        div.className = `shopping-item ${item.comprado ? 'purchased' : ''}`;
        
        const checkedAttr = item.comprado ? 'checked' : '';
        const userActionText = item.actualizado_por_nombre 
            ? `<span class="shopping-item-meta">Actualizado por: ${item.actualizado_por_nombre}</span>` 
            : '';

        div.innerHTML = `
            <div class="shopping-item-left">
                <input type="checkbox" class="shopping-checkbox" ${checkedAttr} id="chk-${item.id}">
                <div>
                    <div class="shopping-item-name">${item.nombre}</div>
                    ${userActionText}
                </div>
            </div>
            <div style="display: flex; align-items: center; gap: 1rem;">
                <span class="shopping-qty-badge">${item.cantidad} ${item.unidad}</span>
                <button class="btn-secondary" style="padding: 0.3rem 0.6rem; font-size: 0.8rem; background: none; border-color: transparent;" onclick="deleteShoppingItem(${item.id})">❌</button>
            </div>
        `;

        // Event listener para el toggle de compra con control de concurrencia optimista
        div.querySelector('.shopping-checkbox').addEventListener('change', (e) => {
            toggleShoppingItem(item.id, e.target.checked ? 1 : 0, item.version || 1);
        });

        container.appendChild(div);
    });
}

async function addShoppingItem(force = false) {
    const nameInput = document.getElementById('shop-item-name');
    const qtyInput = document.getElementById('shop-item-qty');
    const unitSelect = document.getElementById('shop-item-unit');

    const nombre = nameInput.value.trim();
    if (!nombre) return;

    const payload = {
        lista_id: state.shoppingList.id,
        nombre: nombre,
        cantidad: parseInt(qtyInput.value),
        unidad: unitSelect.value,
        force: force
    };

    try {
        const { data } = await apiFetch(`${CONFIG.apiShopping}?action=add_item`, {
            method: 'POST',
            body: JSON.stringify(payload)
        });

        // Comprobación difusa de duplicados en Python
        if (data.duplicate) {
            openConfirmModal(
                "Artículo Similar Detectado",
                `<p>${data.error}</p><p>¿Estás seguro de que quieres agregarlo de todas formas?</p>`,
                () => {
                    // Si confirma, re-intenta forzando la creación
                    addShoppingItem(true);
                }
            );
            return;
        }

        if (data.success) {
            showToast("Artículo agregado a la lista.", "success");
            nameInput.value = '';
            qtyInput.value = '1';
            loadShoppingList();
        } else {
            showToast(data.error || 'Error al agregar.', 'error');
        }

    } catch (e) {
        console.error("Error al agregar item de compra", e);
    }
}

async function toggleShoppingItem(itemId, comprado, version) {
    try {
        const { data } = await apiFetch(`${CONFIG.apiShopping}?action=toggle_item`, {
            method: 'POST',
            body: JSON.stringify({
                id: itemId,
                comprado: comprado,
                version: version
            })
        });

        if (data.concurrency_error) {
            showToast(data.error, 'error');
            loadShoppingList(); // Recargar para obtener el estado real actualizado por otro familiar
            return;
        }

        if (data.success) {
            showToast(comprado ? "Artículo comprado." : "Artículo marcado pendiente.", "success");
            loadShoppingList();
        } else {
            showToast(data.error, 'error');
        }
    } catch (e) {
        console.error("Error al alternar item", e);
    }
}

async function deleteShoppingItem(itemId) {
    if (!confirm("¿Seguro que deseas eliminar este artículo de la lista?")) return;
    try {
        const { data } = await apiFetch(`${CONFIG.apiShopping}?action=delete_item`, {
            method: 'POST',
            body: JSON.stringify({ id: itemId })
        });
        if (data.success) {
            showToast("Artículo eliminado.", "success");
            loadShoppingList();
        } else {
            showToast(data.error, 'error');
        }
    } catch (e) {
        console.error("Error al eliminar item", e);
    }
}

// --- MODAL DE CONFIRMACIÓN CUSTOM (Para flujos interactivos de fuerza de datos) ---
let confirmCallback = null;

function openConfirmModal(title, bodyHtml, onProceed) {
    document.getElementById('confirm-title').textContent = title;
    document.getElementById('confirm-body').innerHTML = bodyHtml;
    confirmCallback = onProceed;
    document.getElementById('modal-confirm').classList.add('active');
}

function closeConfirmModal() {
    document.getElementById('modal-confirm').classList.remove('active');
    confirmCallback = null;
}

// --- GESTIÓN DE EVENTOS DEL DOM ---
function registerEventListeners() {
    // 1. Selector de Tema Claro/Oscuro
    document.getElementById('theme-toggle').addEventListener('click', toggleTheme);

    // 2. Transición de Formularios de Registro / Login / Recuperación
    document.getElementById('to-register').addEventListener('click', (e) => {
        e.preventDefault();
        document.getElementById('card-login').style.display = 'none';
        document.getElementById('card-recover').style.display = 'none';
        document.getElementById('card-register').style.display = 'block';
    });
    
    document.getElementById('to-login').addEventListener('click', (e) => {
        e.preventDefault();
        document.getElementById('card-register').style.display = 'none';
        document.getElementById('card-recover').style.display = 'none';
        document.getElementById('card-login').style.display = 'block';
    });

    document.getElementById('to-recover').addEventListener('click', (e) => {
        e.preventDefault();
        document.getElementById('card-login').style.display = 'none';
        document.getElementById('card-register').style.display = 'none';
        
        // Reiniciar vistas y inputs de recuperación
        document.getElementById('form-request-recover').reset();
        document.getElementById('form-reset-password').reset();
        document.getElementById('form-request-recover').style.display = 'block';
        document.getElementById('form-reset-password').style.display = 'none';
        document.getElementById('dev-code-notice').style.display = 'none';
        document.getElementById('recover-instructions').textContent = 'Ingresa tu correo para recibir un código de verificación de 6 dígitos.';
        
        document.getElementById('card-recover').style.display = 'block';
        document.getElementById('recover-email').focus();
    });

    document.getElementById('recover-to-login').addEventListener('click', (e) => {
        e.preventDefault();
        document.getElementById('card-recover').style.display = 'none';
        document.getElementById('card-register').style.display = 'none';
        document.getElementById('card-login').style.display = 'block';
    });

    // 3. Envío de Formulario de Registro
    document.getElementById('form-register').addEventListener('submit', async (e) => {
        e.preventDefault();
        const nombre = document.getElementById('reg-name').value;
        const email = document.getElementById('reg-email').value;
        const password = document.getElementById('reg-password').value;

        try {
            const { data } = await apiFetch(`${CONFIG.apiAuth}?action=register`, {
                method: 'POST',
                body: JSON.stringify({ nombre, email, password })
            });

            if (data.success) {
                showToast("¡Registro exitoso! Por favor inicia sesión.", "success");
                document.getElementById('form-register').reset();
                document.getElementById('to-login').click();
            } else {
                showToast(data.error, "error");
            }
        } catch (err) {}
    });

    // 4. Envío de Formulario de Login
    document.getElementById('form-login').addEventListener('submit', async (e) => {
        e.preventDefault();
        const email = document.getElementById('login-email').value;
        const password = document.getElementById('login-password').value;

        try {
            const { data } = await apiFetch(`${CONFIG.apiAuth}?action=login`, {
                method: 'POST',
                body: JSON.stringify({ email, password })
            });

            if (data.success) {
                state.user = data.user;
                state.group = data.group;
                
                localStorage.setItem('user', JSON.stringify(data.user));
                if (data.group) {
                    localStorage.setItem('group', JSON.stringify(data.group));
                }
                
                showToast(`¡Hola ${data.user.nombre}!`, "success");
                updateUIForAuthenticatedUser();
            } else {
                showToast(data.error || "Datos incorrectos", "error");
            }
        } catch (err) {}
    });

    // 5. Botón de Salida (Cerrar Sesión)
    document.getElementById('logout-btn').addEventListener('click', handleLogout);

    // 6. Configuración de Grupo (Crear / Unirse)
    document.getElementById('form-create-group').addEventListener('submit', async (e) => {
        e.preventDefault();
        const nombre = document.getElementById('new-group-name').value.trim();
        try {
            const { data } = await apiFetch(`${CONFIG.apiAuth}?action=create_group`, {
                method: 'POST',
                body: JSON.stringify({ nombre })
            });
            if (data.success) {
                state.group = data.group;
                localStorage.setItem('group', JSON.stringify(data.group));
                showToast("Grupo creado con éxito.", "success");
                updateUIForAuthenticatedUser();
            } else {
                showToast(data.error, "error");
            }
        } catch (err) {}
    });

    document.getElementById('form-join-group').addEventListener('submit', async (e) => {
        e.preventDefault();
        const codigo = document.getElementById('join-group-code').value.trim();
        try {
            const { data } = await apiFetch(`${CONFIG.apiAuth}?action=join_group`, {
                method: 'POST',
                body: JSON.stringify({ codigo_acceso: codigo })
            });
            if (data.success) {
                state.group = data.group;
                localStorage.setItem('group', JSON.stringify(data.group));
                showToast("Te has unido al grupo.", "success");
                updateUIForAuthenticatedUser();
            } else {
                showToast(data.error, "error");
            }
        } catch (err) {}
    });

    // 7. Navegación entre Pestañas (Calendario / Compras)
    document.querySelectorAll('[data-tab]').forEach(btn => {
        btn.addEventListener('click', (e) => {
            document.querySelectorAll('[data-tab]').forEach(b => b.classList.remove('active'));
            e.target.classList.add('active');
            
            const targetTab = e.target.dataset.tab;
            state.activeTab = targetTab;
            
            // Resetear pintor al cambiar de pestaña
            state.selectedPaintShift = null;
            document.querySelectorAll('.btn-shift-painter').forEach(b => b.classList.remove('active'));
            
            if (targetTab === 'calendar') {
                document.getElementById('tab-calendar').style.display = 'block';
                document.getElementById('tab-shopping').style.display = 'none';
                loadEvents();
            } else {
                document.getElementById('tab-calendar').style.display = 'none';
                document.getElementById('tab-shopping').style.display = 'block';
                loadShoppingList();
            }
        });
    });

    // 8. Controles del Mes del Calendario
    document.getElementById('cal-prev').addEventListener('click', () => {
        state.currentDate.setMonth(state.currentDate.getMonth() - 1);
        renderCalendar();
    });
    document.getElementById('cal-next').addEventListener('click', () => {
        state.currentDate.setMonth(state.currentDate.getMonth() + 1);
        renderCalendar();
    });

    // 9. Botón Nuevo Evento
    document.getElementById('btn-new-event').addEventListener('click', () => {
        // Inicializar con fecha y hora de hoy
        const now = new Date();
        const formatZero = (num) => String(num).padStart(2, '0');
        const dateStr = `${now.getFullYear()}-${formatZero(now.getMonth()+1)}-${formatZero(now.getDate())}`;
        const startStr = `${dateStr}T12:00`;
        const endStr = `${dateStr}T13:00`;
        openEventModal({ fecha_inicio: startStr, fecha_fin: endStr });
    });

    // 10. Controles del Modal de Eventos
    document.getElementById('event-modal-close').addEventListener('click', closeEventModal);
    document.getElementById('event-cancel-btn').addEventListener('click', closeEventModal);
    
    document.getElementById('form-event').addEventListener('submit', (e) => {
        e.preventDefault();
        saveEvent();
    });

    document.getElementById('event-delete-btn').addEventListener('click', async () => {
        const eventId = document.getElementById('event-id').value;
        if (!eventId || !confirm("¿Seguro que deseas eliminar esta actividad?")) return;
        
        try {
            const { data } = await apiFetch(`${CONFIG.apiEvents}?action=delete`, {
                method: 'POST',
                body: JSON.stringify({ id: parseInt(eventId) })
            });
            if (data.success) {
                showToast("Actividad eliminada.", "success");
                closeEventModal();
                loadEvents();
            } else {
                showToast(data.error, "error");
            }
        } catch (e) {}
    });

    // 11. Envío de Formulario para añadir compras
    document.getElementById('form-shopping-add').addEventListener('submit', (e) => {
        e.preventDefault();
        addShoppingItem();
    });

    // 12. Modal de Confirmación Custom
    document.getElementById('confirm-close').addEventListener('click', closeConfirmModal);
    document.getElementById('confirm-no-btn').addEventListener('click', closeConfirmModal);
    
    document.getElementById('confirm-yes-btn').addEventListener('click', () => {
        if (confirmCallback) {
            confirmCallback();
        }
        closeConfirmModal();
    });

    // 13. Pintor Rápido de Turnos
    document.querySelectorAll('.btn-shift-painter').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const clickedBtn = e.currentTarget;
            const shiftType = clickedBtn.dataset.paintShift;
            
            if (clickedBtn.classList.contains('active')) {
                clickedBtn.classList.remove('active');
                state.selectedPaintShift = null;
            } else {
                document.querySelectorAll('.btn-shift-painter').forEach(b => b.classList.remove('active'));
                clickedBtn.classList.add('active');
                state.selectedPaintShift = shiftType;
            }
        });
    });

    // 14. Envío de Formulario para solicitar código de recuperación
    document.getElementById('form-request-recover').addEventListener('submit', async (e) => {
        e.preventDefault();
        const email = document.getElementById('recover-email').value.trim();
        
        try {
            const { data } = await apiFetch(`${CONFIG.apiAuth}?action=request_reset`, {
                method: 'POST',
                body: JSON.stringify({ email })
            });
            
            if (data.success) {
                showToast("Código de verificación generado.", "success");
                
                document.getElementById('form-request-recover').style.display = 'none';
                document.getElementById('form-reset-password').style.display = 'block';
                document.getElementById('recover-instructions').textContent = `Hemos generado un código para ${email}. Introduce el código e ingresa tu nueva contraseña.`;
                
                if (data.dev_token) {
                    const notice = document.getElementById('dev-code-notice');
                    notice.innerHTML = `⚙️ [Modo Desarrollo]<br>Código generado: <strong>${data.dev_token}</strong>`;
                    notice.style.display = 'block';
                    document.getElementById('reset-code').value = data.dev_token;
                }
                
                document.getElementById('reset-code').focus();
            } else {
                showToast(data.error || "No se pudo procesar la solicitud.", "error");
            }
        } catch (err) {}
    });

    // 15. Envío de Formulario para restablecer contraseña con el código
    document.getElementById('form-reset-password').addEventListener('submit', async (e) => {
        e.preventDefault();
        const email = document.getElementById('recover-email').value.trim();
        const token = document.getElementById('reset-code').value.trim();
        const new_password = document.getElementById('reset-password').value;
        
        try {
            const { data } = await apiFetch(`${CONFIG.apiAuth}?action=reset_password`, {
                method: 'POST',
                body: JSON.stringify({ email, token, new_password })
            });
            
            if (data.success) {
                showToast("Contraseña restablecida con éxito.", "success");
                
                document.getElementById('card-recover').style.display = 'none';
                document.getElementById('card-login').style.display = 'block';
                document.getElementById('form-login').reset();
                document.getElementById('login-email').value = email;
                document.getElementById('login-password').focus();
            } else {
                showToast(data.error || "Código incorrecto o expirado.", "error");
            }
        } catch (err) {}
    });
}

function handleLogout() {
    state.user = null;
    state.group = null;
    state.selectedPaintShift = null; // resetear pintor
    document.querySelectorAll('.btn-shift-painter').forEach(b => b.classList.remove('active'));
    
    localStorage.removeItem('user');
    localStorage.removeItem('group');
    
    document.getElementById('user-display').style.display = 'none';
    document.getElementById('logout-btn').style.display = 'none';
    document.getElementById('app-tabs').style.display = 'none';
    
    // Reset views
    document.getElementById('form-login').reset();
    document.getElementById('form-register').reset();
    document.getElementById('form-request-recover').reset();
    document.getElementById('form-reset-password').reset();
    document.getElementById('card-register').style.display = 'none';
    document.getElementById('card-recover').style.display = 'none';
    document.getElementById('card-login').style.display = 'block';
    
    showToast("Sesión cerrada.", "success");
    showView('view-auth');
}

// --- UTILERÍAS ---
function showToast(message, type = 'success') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast-msg ${type}`;
    toast.textContent = message;
    
    container.appendChild(toast);
    
    // Desvanecer y remover después de 4 segundos
    setTimeout(() => {
        toast.style.transition = 'opacity 0.5s ease';
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 500);
    }, 3500);
}
