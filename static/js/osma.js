(() => {
    'use strict';

    const $ = id => document.getElementById(id);
    const esc = s => String(s ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');
    const norm = s => String(s ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
    
    // Formato de moneda venezolana
    const fmt = n => Number(n || 0).toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const parseMoney = v => {
        if (!v) return 0;
        let s = String(v).trim();
        if (s.includes(',') && s.includes('.')) {
            if (s.indexOf('.') < s.indexOf(',')) {
                s = s.replaceAll('.', '').replace(',', '.');
            } else {
                s = s.replaceAll(',', '');
            }
        } else if (s.includes(',')) {
            s = s.replace(',', '.');
        }
        let val = Number.parseFloat(s);
        return Number.isNaN(val) ? 0 : val;
    };

    let allProducts = [];
    let recentEntries = [];
    let currentEntriesPage = 1;
    let totalEntriesPages = 1;
    let availableLots = [];
    let cart = [];
    let currentSaleToken = null; // Token de idempotencia persistente por intento de venta
    let selectedProductId = null;
    window.saleRatesFrozen = false; // Congelador de tasa en cobro activo

    // Mensaje de notificación
    function info(msg, isError = false) {
        const el = $('notice');
        if (!el) return;
        el.textContent = msg;
        el.className = 'notice ' + (isError ? 'error' : '');
        if (msg) {
            clearTimeout(window._noticeTimer);
            window._noticeTimer = setTimeout(() => { el.textContent = ''; }, 6000);
        }
    }

    // Cabecera CSRF para Django con lectura robusta de cookie y token en DOM
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    function getHeaders() {
        const token = getCookie('csrftoken') || window.CSRF_TOKEN || '';
        return {
            'Content-Type': 'application/json',
            'X-CSRFToken': token
        };
    }

    // -------------------------------------------------------------------------
    // NAVEGACIÓN ENTRE PESTAÑAS
    // -------------------------------------------------------------------------
    document.querySelectorAll('.nav button').forEach(btn => {
        btn.onclick = () => {
            const tab = btn.dataset.tab;
            document.querySelectorAll('.nav button').forEach(b => b.setAttribute('aria-selected', 'false'));
            btn.setAttribute('aria-selected', 'true');
            ['entry', 'sell', 'stock', 'expenses', 'refill'].forEach(id => {
                const el = $(id);
                if (el) el.hidden = (id !== tab);
            });
            if (tab === 'entry') void loadRecentEntries();
            if (tab === 'sell') void loadLots();
            if (tab === 'stock') void loadInventoryMetrics();
            if (tab === 'expenses') void loadExpenses();
            if (tab === 'refill') void loadReport();
        };
    });

    // -------------------------------------------------------------------------
    // TASAS DE CAMBIO EN VIVO (BCV / USDT)
    // -------------------------------------------------------------------------
    async function loadRates() {
        try {
            const res = await fetch('/api/tasas/');
            const data = await res.json();
            if (data.usd_bcv) {
                if ($('bar-usd-rate')) $('bar-usd-rate').textContent = 'Bs ' + fmt(data.usd_bcv);
                // Si hay un cobro en curso con carrito activo, NO sobreescribir la tasa congelada
                if (!window.saleRatesFrozen && $('rate-usd')) {
                    $('rate-usd').value = data.usd_bcv.toFixed(2).replace('.', ',');
                }
            }
            if (data.usdt) {
                if ($('bar-usdt-rate')) $('bar-usdt-rate').textContent = 'Bs ' + fmt(data.usdt);
                if (!window.saleRatesFrozen && $('rate-usdt')) {
                    $('rate-usdt').value = data.usdt.toFixed(2).replace('.', ',');
                }
            }
            if (data.fecha_actualizacion && $('rates-updated-text')) {
                $('rates-updated-text').textContent = 'Actualizado: ' + data.fecha_actualizacion;
            }
            updatePaymentCalculations();
        } catch (e) {
            console.error('Error cargando tasas:', e);
        }
    }

    if ($('btn-sync-rates')) {
        $('btn-sync-rates').onclick = async () => {
            $('btn-sync-rates').disabled = true;
            $('btn-sync-rates').textContent = 'Consultando BCV...';
            try {
                const res = await fetch('/api/tasas/actualizar/', {
                    method: 'POST',
                    headers: getHeaders(),
                    body: JSON.stringify({})
                });
                const data = await res.json();
                if (data.exito) {
                    info('Tasas actualizadas exitosamente con el BCV.');
                    await loadRates();
                } else {
                    info(data.mensaje || 'No se pudo conectar al BCV. Se conservó la última tasa válida.', true);
                }
            } catch (e) {
                console.error('Error sincronizando tasas:', e);
                info('Error al intentar sincronizar tasas.', true);
            } finally {
                $('btn-sync-rates').disabled = false;
                $('btn-sync-rates').textContent = '⟳ Actualizar tasas BCV';
            }
        };
    }

    // Actualización automática de tasas cada 15 minutos en segundo plano
    setInterval(async () => {
        try {
            await fetch('/api/tasas/actualizar/', {
                method: 'POST',
                headers: getHeaders(),
                body: JSON.stringify({})
            });
            await loadRates();
        } catch (e) {
            console.log('Sincronización periódica automática:', e);
        }
    }, 15 * 60 * 1000);

    // -------------------------------------------------------------------------
    // 01 · ENTRADA DE PRODUCTOS (REGISTRAR ARRIBA + HISTORIAL PAGINADO DEBAJO)
    // -------------------------------------------------------------------------
    async function loadProducts() {
        try {
            const res = await fetch('/api/productos/');
            const data = await res.json();
            allProducts = data.productos || [];
            renderSuggestions();
            renderSellProductChoices();
            renderStockList();
        } catch (e) {
            console.error('Error cargando productos:', e);
        }
    }

    async function loadEntries(page = 1) {
        currentEntriesPage = page;
        const search = $('entry-search') ? $('entry-search').value.trim() : '';
        const filterType = $('entry-date-filter') ? $('entry-date-filter').value : 'all';
        const singleDate = $('entry-date-single') ? $('entry-date-single').value : '';
        const monthDate = $('entry-date-month') ? $('entry-date-month').value : '';
        const fromDate = $('entry-date-from') ? $('entry-date-from').value : '';
        const toDate = $('entry-date-to') ? $('entry-date-to').value : '';

        const params = new URLSearchParams({
            page: page,
            page_size: 10
        });
        if (search) params.append('q', search);
        if (filterType && filterType !== 'all') {
            params.append('filtro_fecha', filterType);
            if (filterType === 'dia' && singleDate) params.append('fecha', singleDate);
            if (filterType === 'mes' && monthDate) params.append('mes', monthDate);
            if (filterType === 'rango') {
                if (fromDate) params.append('desde', fromDate);
                if (toDate) params.append('hasta', toDate);
            }
        }

        try {
            const res = await fetch(`/api/entradas/?${params.toString()}`);
            const data = await res.json();
            recentEntries = data.entradas || [];
            totalEntriesPages = data.total_paginas || 1;
            renderRecentEntries(data.total_entradas || 0, data.pagina_actual || 1, totalEntriesPages);
        } catch (e) {
            console.error('Error cargando entradas:', e);
        }
    }

    // Control de filtros de fecha en historial de entradas
    if ($('entry-date-filter')) {
        $('entry-date-filter').onchange = () => {
            const val = $('entry-date-filter').value;
            if ($('entry-date-single')) $('entry-date-single').style.display = (val === 'dia') ? 'inline-block' : 'none';
            if ($('entry-date-month')) $('entry-date-month').style.display = (val === 'mes') ? 'inline-block' : 'none';
            if ($('entry-date-from')) $('entry-date-from').style.display = (val === 'rango') ? 'inline-block' : 'none';
            if ($('entry-date-to')) $('entry-date-to').style.display = (val === 'rango') ? 'inline-block' : 'none';
            if (val === 'all' || val === 'hoy') {
                void loadEntries(1);
            }
        };
    }
    if ($('btn-filter-entries')) $('btn-filter-entries').onclick = () => void loadEntries(1);
    if ($('btn-reset-entries')) {
        $('btn-reset-entries').onclick = () => {
            if ($('entry-search')) $('entry-search').value = '';
            if ($('entry-date-filter')) $('entry-date-filter').value = 'all';
            if ($('entry-date-single')) $('entry-date-single').style.display = 'none';
            if ($('entry-date-month')) $('entry-date-month').style.display = 'none';
            if ($('entry-date-from')) $('entry-date-from').style.display = 'none';
            if ($('entry-date-to')) $('entry-date-to').style.display = 'none';
            void loadEntries(1);
        };
    }
    if ($('entry-search')) {
        $('entry-search').onkeydown = e => {
            if (e.key === 'Enter') {
                e.preventDefault();
                void loadEntries(1);
            }
        };
    }
    if ($('btn-entry-prev')) $('btn-entry-prev').onclick = () => void loadEntries(currentEntriesPage - 1);
    if ($('btn-entry-next')) $('btn-entry-next').onclick = () => void loadEntries(currentEntriesPage + 1);

    function renderSuggestions() {
        const query = norm($('lookup').value);
        if (!query) {
            $('suggest').innerHTML = '';
            return;
        }
        const matches = allProducts.filter(p => norm(p.nombre).includes(query)).slice(0, 5);
        $('suggest').innerHTML = matches.map(p => 
            `<button type="button" class="secondary" data-pick="${p.id}" style="padding: 6px 12px; font-size: .8rem;">${esc(p.nombre)}</button>`
        ).join('');
    }

    $('lookup').oninput = renderSuggestions;

    $('suggest').onclick = e => {
        const btn = e.target.closest('[data-pick]');
        if (!btn) return;
        const id = Number(btn.dataset.pick);
        const p = allProducts.find(x => x.id === id);
        if (!p) return;

        selectedProductId = p.id;
        $('name').value = p.nombre;
        $('name').readOnly = true;
        $('minimum').value = p.stock_minimo;
        if (p.ultimo_costo > 0) $('cost').value = p.ultimo_costo.toFixed(2).replace('.', ',');
        if (p.ultimo_precio > 0) $('price').value = p.ultimo_precio.toFixed(2).replace('.', ',');
        $('clear-selection').hidden = false;
        $('suggest').innerHTML = '';
        info(`Producto "${p.nombre}" seleccionado. Ingresa la nueva cantidad recibida.`);
    };

    function resetEntryForm() {
        selectedProductId = null;
        window._confirmarCoincidenciaEntrada = false;
        $('entry-form').reset();
        $('name').readOnly = false;
        $('clear-selection').hidden = true;
        $('suggest').innerHTML = '';
        $('minimum').value = '3';
    }

    $('clear-selection').onclick = resetEntryForm;

    async function handleSaveEntry(e) {
        e?.preventDefault?.();
        const nombre = $('name').value.trim();
        const cantidad = Number.parseInt($('quantity').value, 10);
        const stock_minimo = Number.parseInt($('minimum').value, 10) || 3;
        const costo_unitario = parseMoney($('cost').value);
        const precio_venta = parseMoney($('price').value);

        if (!nombre) {
            info('Por favor indica el nombre del producto.', true);
            $('name').focus();
            return;
        }
        if (Number.isNaN(cantidad) || cantidad <= 0) {
            info('Por favor indica una cantidad de unidades mayor a 0.', true);
            $('quantity').focus();
            return;
        }
        if (costo_unitario < 0) {
            info('El costo unitario no puede ser negativo.', true);
            $('cost').focus();
            return;
        }
        if (precio_venta <= 0) {
            info('El precio de venta debe ser mayor a 0.', true);
            $('price').focus();
            return;
        }

        $('btn-save-entry').disabled = true;
        $('btn-save-entry').textContent = 'Guardando...';
        try {
            const res = await fetch('/api/entradas/', {
                method: 'POST',
                headers: getHeaders(),
                body: JSON.stringify({
                    producto_id: selectedProductId,
                    nombre: nombre,
                    cantidad: cantidad,
                    stock_minimo: stock_minimo,
                    costo_unitario: costo_unitario,
                    precio_venta: precio_venta,
                    confirmar_coincidencia: window._confirmarCoincidenciaEntrada || false
                })
            });
            const data = await res.json();
            if (data.advertencia_coincidencia) {
                const conf = confirm(`${data.mensaje}\n\n¿Deseas registrar este producto como un producto/tono/presentación nuevo independiente?`);
                if (conf) {
                    window._confirmarCoincidenciaEntrada = true;
                    return handleSaveEntry(e);
                }
                return;
            }
            window._confirmarCoincidenciaEntrada = false;

            if (!res.ok) {
                info(data.error || 'Error al guardar entrada.', true);
            } else {
                info(data.mensaje);
                resetEntryForm();
                await Promise.all([
                    loadProducts(),
                    loadEntries(1),
                    loadLots(),
                    loadInventoryMetrics()
                ]);
            }
        } catch (err) {
            console.error('Error de red al guardar entrada:', err);
            info('Error de red al guardar entrada.', true);
        } finally {
            $('btn-save-entry').disabled = false;
            $('btn-save-entry').textContent = 'Guardar entrada';
        }
    }

    $('btn-save-entry').onclick = handleSaveEntry;
    $('entry-form').onsubmit = handleSaveEntry;
    $('entry-form').onkeydown = e => {
        if (e.key === 'Enter') {
            e.preventDefault();
            void handleSaveEntry(e);
        }
    };

    function renderRecentEntries(totalCount = 0, currentPage = 1, totalPages = 1) {
        const el = $('recent-entries');
        if (!el) return;
        if (!recentEntries.length) {
            el.innerHTML = '<div class="empty">No se encontraron movimientos para el filtro seleccionado.</div>';
            if ($('entry-pagination')) $('entry-pagination').style.display = 'none';
            return;
        }

        el.innerHTML = recentEntries.map(e => `
            <div class="row" style="align-items: flex-start; padding: 10px 0; border-bottom: 1px solid var(--line);">
                <div style="flex: 1; padding-right: 12px;">
                    <b class="product-title-wrap" style="display: block; font-size: 0.95rem;">${esc(e.producto_nombre)}</b>
                    <small style="display: block; color: var(--muted); margin-top: 3px;">
                        ${esc(e.fecha_hora_12h || e.fecha)} · ${e.cantidad_recibida} uds recibidas (${e.cantidad_disponible} disp. · ${e.unidades_vendidas || 0} vendidas)
                    </small>
                    ${e.observaciones ? `<small class="muted" style="display: block; font-style: italic;">Nota: ${esc(e.observaciones)}</small>` : ''}
                    ${e.puede_anular ? `
                        <button type="button" class="link" data-delete-entry="${e.id}" style="color: #b3382c; font-size: .78rem; padding: 0; margin-top: 6px;">
                            ✕ Anular esta entrada
                        </button>
                    ` : `
                        <span style="color: #888; font-size: .76rem; display: inline-block; margin-top: 6px;" title="No se puede anular: ya se vendieron unidades de este lote">
                            🔒 Entrada con ventas asociadas (no anulable)
                        </span>
                    `}
                </div>
                <div style="text-align: right; white-space: nowrap;">
                    <span class="amount" style="font-size: 1.05rem;">Bs ${fmt(e.precio_venta)}</span>
                    <small class="muted" style="display: block;">Costo: Bs ${fmt(e.costo_unitario)}</small>
                </div>
            </div>
        `).join('');

        const pagination = $('entry-pagination');
        if (pagination) {
            pagination.style.display = (totalPages > 1 || recentEntries.length >= 10) ? 'flex' : 'none';
            if ($('entry-page-info')) $('entry-page-info').textContent = `Página ${currentPage} de ${totalPages} (Total: ${totalCount})`;
            if ($('btn-entry-prev')) $('btn-entry-prev').disabled = currentPage <= 1;
            if ($('btn-entry-next')) $('btn-entry-next').disabled = currentPage >= totalPages;
        }
    }

    $('recent-entries').onclick = async e => {
        const btn = e.target.closest('[data-delete-entry]');
        if (!btn) return;
        const entryId = Number(btn.dataset.deleteEntry);
        if (!confirm('¿Deseas anular esta entrada de mercancía? Sus unidades se descontarán del inventario.')) return;

        try {
            const res = await fetch(`/api/entradas/${entryId}/eliminar/`, {
                method: 'POST',
                headers: getHeaders()
            });
            const data = await res.json();
            if (res.ok) {
                info(data.mensaje);
                await Promise.all([
                    loadProducts(),
                    loadEntries(currentEntriesPage),
                    loadLots(),
                    loadInventoryMetrics()
                ]);
            } else {
                info(data.error || 'No se pudo anular la entrada.', true);
            }
        } catch (err) {
            console.error('Error anulando entrada:', err);
            info('Error de red al intentar anular entrada.', true);
        }
    };

    // -------------------------------------------------------------------------
    // 02 · VENTAS Y COBRO MIXTO (DÓLARES BCV, USDT SEPARADO, PENDIENTE DUAL)
    // -------------------------------------------------------------------------
    async function loadLots() {
        try {
            let res = await fetch('/api/lotes/disponibles/');
            if (!res.ok) {
                res = await fetch('/api/inventario/lotes/');
            }
            const data = await res.json();
            availableLots = data.lotes || [];
            renderSellProductChoices();
        } catch (e) {
            console.error('Error cargando lotes:', e);
        }
    }

    function renderSellProductChoices() {
        const select = $('sell-product-select');
        const searchVal = norm($('sell-search').value);
        if (!select) return;

        const filteredLots = availableLots.filter(l => norm(l.producto_nombre).includes(searchVal));

        if (!filteredLots.length) {
            select.innerHTML = '<option value="">No hay productos disponibles en inventario</option>';
            $('sell-unit-price').value = '';
            return;
        }

        select.innerHTML = filteredLots.map(l => 
            `<option value="${l.lote_id}" data-price="${l.precio_venta}" data-prod="${l.producto_id}" data-max="${l.cantidad_disponible}">
                ${esc(l.producto_nombre)} · ${l.cantidad_disponible} disp. (${l.fecha_hora_12h || l.fecha}) - Bs ${fmt(l.precio_venta)}
            </option>`
        ).join('');

        const selectedOpt = select.options[select.selectedIndex];
        if (selectedOpt && selectedOpt.dataset.price) {
            $('sell-unit-price').value = Number(selectedOpt.dataset.price).toFixed(2).replace('.', ',');
        }
    }

    $('sell-search').oninput = renderSellProductChoices;
    $('sell-product-select').onchange = () => {
        const opt = $('sell-product-select').options[$('sell-product-select').selectedIndex];
        if (opt && opt.dataset.price) {
            $('sell-unit-price').value = Number(opt.dataset.price).toFixed(2).replace('.', ',');
        }
    };

    function _agregarLoteAlCarrito(opt, unidades, precioUnitario) {
        const loteId = Number(opt.value);
        const prodId = Number(opt.dataset.prod);
        const maxAvailable = Number(opt.dataset.max);
        const prodName = opt.text.split('·')[0].trim();

        const existing = cart.find(x => x.lote_id === loteId);
        const currentQtyInCart = existing ? existing.cantidad : 0;

        if ((currentQtyInCart + unidades) > maxAvailable) {
            info(`Solo quedan ${maxAvailable} unidades disponibles en este lote. Tienes ${currentQtyInCart} en la venta.`, true);
            return false;
        }

        if (existing) {
            existing.cantidad += unidades;
            existing.precio_unitario_bs = precioUnitario;
        } else {
            cart.push({
                producto_id: prodId,
                lote_id: loteId,
                nombre: prodName,
                cantidad: unidades,
                precio_unitario_bs: precioUnitario
            });
        }
        return true;
    }

    $('add-cart').onclick = () => {
        const select = $('sell-product-select');
        const opt = select.options[select.selectedIndex];
        if (!opt || !opt.value) {
            info('Selecciona un producto disponible.', true);
            return;
        }

        const unidades = Number.parseInt($('units').value, 10);
        const precioUnitario = parseMoney($('sell-unit-price').value);

        if (Number.isNaN(unidades) || unidades <= 0) {
            info('Ingresa una cantidad mayor a 0.', true);
            return;
        }
        if (precioUnitario <= 0) {
            info('El precio de venta debe ser mayor a 0.', true);
            return;
        }

        const agregado = _agregarLoteAlCarrito(opt, unidades, precioUnitario);
        if (!agregado) return;

        // Congelar tasas de la venta activa
        window.saleRatesFrozen = true;
        currentSaleToken = null; // Reiniciar token al cambiar ítems

        renderCart();
        updatePaymentCalculations();
        info('Producto agregado a la venta actual.');
    };

    function renderCart() {
        const el = $('cart');
        if (!cart.length) {
            el.innerHTML = '<div class="empty">La venta actual está vacía. Agrega productos de la izquierda.</div>';
            $('sale-total').textContent = 'Bs 0,00';
            window.saleRatesFrozen = false;
            updatePaymentCalculations();
            return;
        }

        let total = 0;
        el.innerHTML = cart.map((item, idx) => {
            const subtotal = item.cantidad * item.precio_unitario_bs;
            total += subtotal;
            return `
                <div class="row">
                    <div>
                        <b>${esc(item.nombre)}</b>
                        <small>${item.cantidad} x Bs ${fmt(item.precio_unitario_bs)}</small>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span class="amount">Bs ${fmt(subtotal)}</span>
                        <button type="button" class="link" data-remove-item="${idx}" style="color: #b3382c; font-size: .8rem;">✕</button>
                    </div>
                </div>
            `;
        }).join('');

        $('sale-total').textContent = 'Bs ' + fmt(total);
    }

    $('cart').onclick = e => {
        const btn = e.target.closest('[data-remove-item]');
        if (btn) {
            const idx = Number(btn.dataset.removeItem);
            cart.splice(idx, 1);
            currentSaleToken = null;
            if (!cart.length) window.saleRatesFrozen = false;
            renderCart();
            updatePaymentCalculations();
        }
    };

    // -------------------------------------------------------------------------
    // CÁLCULO EN TIEMPO REAL DE COBRO MIXTO, SALDO PENDIENTE DUAL Y VUELTO REAL
    // -------------------------------------------------------------------------
    function updatePaymentCalculations() {
        const totalSale = cart.reduce((acc, i) => acc + (i.cantidad * i.precio_unitario_bs), 0);
        const payBs = parseMoney($('pay-bs') ? $('pay-bs').value : 0);
        const payMobile = parseMoney($('pay-mobile') ? $('pay-mobile').value : 0);
        const payPunto = parseMoney($('pay-punto') ? $('pay-punto').value : 0);
        const payUsd = parseMoney($('pay-usd') ? $('pay-usd').value : 0);
        const payUsdt = parseMoney($('pay-usdt') ? $('pay-usdt').value : 0);

        const rateUsd = parseMoney($('rate-usd') ? $('rate-usd').value : 0);
        const rateUsdt = parseMoney($('rate-usdt') ? $('rate-usdt').value : 0);

        // Conversión estricta: Dólares con tasa BCV aplicada; USDT con tasa USDT
        const equivBsCash = payBs;
        const equivMobile = payMobile;
        const equivPunto = payPunto;
        const equivUsd = payUsd * rateUsd;
        const equivUsdt = payUsdt * rateUsdt;
        const totalPaid = equivBsCash + equivMobile + equivPunto + equivUsd + equivUsdt;

        // Actualizar total de la venta en bolívares
        if ($('live-sale-total')) $('live-sale-total').textContent = `Bs ${fmt(totalSale)}`;

        // Monto recibido por cada medio y su moneda original
        const breakdownParts = [];
        if (payBs > 0) breakdownParts.push(`• Efectivo en Bs: <b>Bs ${fmt(payBs)}</b>`);
        if (payMobile > 0) breakdownParts.push(`• Pago Móvil: <b>Bs ${fmt(payMobile)}</b>`);
        if (payPunto > 0) breakdownParts.push(`• Punto de Venta: <b>Bs ${fmt(payPunto)}</b>`);
        if (payUsd > 0) breakdownParts.push(`• Efectivo USD: <b>$ ${fmt(payUsd)}</b> (= Bs ${fmt(equivUsd)} a tasa BCV ${fmt(rateUsd)})`);
        if (payUsdt > 0) breakdownParts.push(`• USDT: <b>${fmt(payUsdt)} USDT</b> (= Bs ${fmt(equivUsdt)} a tasa ${fmt(rateUsdt)})`);

        if ($('live-received-breakdown')) {
            $('live-received-breakdown').innerHTML = breakdownParts.length 
                ? breakdownParts.join('<br>') 
                : '<span class="muted">Sin montos ingresados aún</span>';
        }

        // Total recibido equivalente en bolívares
        if ($('live-total-received')) {
            $('live-total-received').textContent = `Bs ${fmt(totalPaid)}`;
        }

        const pendingBox = $('live-pending-box');
        const pendingText = $('live-pending-text');
        const surplusBox = $('live-surplus-box');
        const surplusText = $('live-surplus-text');
        const surplusDetail = $('live-surplus-detail');

        const diff = totalSale - totalPaid;

        if (diff > 0.05) {
            // Saldo pendiente expresado en ambas monedas (Bs y USD a tasa oficial BCV de la venta)
            const pendingUsd = rateUsd > 0 ? (diff / rateUsd) : 0;
            if (pendingBox) pendingBox.style.display = 'block';
            if (pendingText) {
                pendingText.textContent = `Pendiente: Bs ${fmt(diff)}, equivalentes a USD ${fmt(pendingUsd)} (calculados a tasa BCV ${fmt(rateUsd)} Bs/$)`;
            }
            if (surplusBox) surplusBox.style.display = 'none';
        } else {
            // Cubierto completo o sobrepago con vuelto
            if (pendingBox) pendingBox.style.display = 'none';
            if (surplusBox) surplusBox.style.display = 'block';

            if (Math.abs(diff) <= 0.05) {
                if (surplusText) surplusText.textContent = '¡Pago exacto completado!';
                if (surplusDetail) surplusDetail.textContent = `Cobro neto exacto: Bs ${fmt(totalSale)}`;
            } else {
                const surplusBs = Math.abs(diff);
                const surplusUsd = rateUsd > 0 ? (surplusBs / rateUsd) : 0;
                if (surplusText) surplusText.textContent = `Cambio / Vuelto a entregar en efectivo: Bs ${fmt(surplusBs)}`;
                if (surplusDetail) {
                    surplusDetail.innerHTML = `Monto recibido: <b>Bs ${fmt(totalPaid)}</b> · Vuelto entregado: <b>Bs ${fmt(surplusBs)}</b> (o USD ${fmt(surplusUsd)}) · Cobro neto: <b>Bs ${fmt(totalSale)}</b>`;
                }
            }
        }
    }

    ['pay-bs', 'pay-mobile', 'pay-punto', 'pay-usd', 'pay-usdt', 'rate-usd', 'rate-usdt'].forEach(id => {
        if ($(id)) $(id).oninput = updatePaymentCalculations;
    });

    $('finish').onclick = async () => {
        if (!cart.length) return;
        const totalSale = cart.reduce((acc, i) => acc + (i.cantidad * i.precio_unitario_bs), 0);

        const payBs = parseMoney($('pay-bs').value);
        const payMobile = parseMoney($('pay-mobile').value);
        const payPunto = parseMoney($('pay-punto').value);
        const payUsd = parseMoney($('pay-usd').value);
        const payUsdt = parseMoney($('pay-usdt').value);

        const rateUsd = parseMoney($('rate-usd').value);
        const rateUsdt = parseMoney($('rate-usdt').value);

        const pagosList = [];
        if (payBs > 0) pagosList.push({ metodo: 'EFECTIVO_BS', monto_original: payBs });
        if (payMobile > 0) pagosList.push({ metodo: 'PAGO_MOVIL', monto_original: payMobile });
        if (payPunto > 0) pagosList.push({ metodo: 'PUNTO_VENTA', monto_original: payPunto });
        if (payUsd > 0) {
            if (rateUsd <= 0) { info('Debes indicar una tasa válida para el pago en USD.', true); return; }
            pagosList.push({ metodo: 'EFECTIVO_USD', monto_original: payUsd });
        }
        if (payUsdt > 0) {
            if (rateUsdt <= 0) { info('Debes indicar una tasa válida para el pago en USDT.', true); return; }
            pagosList.push({ metodo: 'USDT', monto_original: payUsdt });
        }

        const totalPaid = payBs + payMobile + payPunto + (payUsd * rateUsd) + (payUsdt * rateUsdt);
        if (totalPaid < (totalSale - 0.50)) {
            info(`El pago recibido (Bs ${fmt(totalPaid)}) es menor que el total (Bs ${fmt(totalSale)}).`, true);
            return;
        }

        $('finish').disabled = true;
        $('finish').textContent = 'Registrando venta...';

        try {
            if (!currentSaleToken) {
                currentSaleToken = (window.crypto && crypto.randomUUID) 
                    ? crypto.randomUUID() 
                    : ('IDEM-' + Date.now() + '-' + Math.random().toString(36).substring(2, 9));
            }
            const clientToken = currentSaleToken;

            const res = await fetch('/api/ventas/', {
                method: 'POST',
                headers: getHeaders(),
                body: JSON.stringify({
                    items: cart,
                    pagos: pagosList,
                    tasa_usd: rateUsd,
                    tasa_usdt: rateUsdt,
                    idempotency_key: clientToken
                })
            });
            if (res.redirected || res.url.includes('/login/')) {
                info('La sesión de la tienda expiró. Redirigiendo al acceso...', true);
                setTimeout(() => { window.location.href = '/login/'; }, 1500);
                return;
            }
            const data = await res.json();
            if (res.ok) {
                let msgExito = `${data.mensaje}`;
                if (data.vuelto_total_bs > 0) {
                    msgExito += ` · Vuelto a entregar al cliente: Bs ${fmt(data.vuelto_total_bs)}.`;
                }
                info(msgExito);

                // Limpiar carrito y descongelar tasas
                cart = [];
                currentSaleToken = null;
                window.saleRatesFrozen = false;
                ['pay-bs', 'pay-mobile', 'pay-punto', 'pay-usd', 'pay-usdt'].forEach(id => {
                    if ($(id)) $(id).value = '0';
                });
                renderCart();
                updatePaymentCalculations();

                await Promise.all([
                    loadProducts(),
                    loadEntries(1),
                    loadLots(),
                    loadInventoryMetrics()
                ]);
            } else {
                info(data.error || 'No se pudo procesar la venta.', true);
            }
        } catch (e) {
            console.error('Error procesando venta:', e);
            info('Error de red al intentar procesar la venta.', true);
        } finally {
            $('finish').disabled = false;
            $('finish').textContent = 'Confirmar y registrar venta';
        }
    };

    // -------------------------------------------------------------------------
    // 03 · INVENTARIO Y EXISTENCIAS
    // -------------------------------------------------------------------------
    async function loadInventoryMetrics() {
        try {
            const res = await fetch('/api/inventario/metricas/');
            const data = await res.json();
            if ($('product-count')) $('product-count').textContent = data.total_productos || 0;
            if ($('stock-count')) $('stock-count').textContent = data.unidades_disponibles || 0;
            if ($('stock-value')) $('stock-value').textContent = 'Bs ' + fmt(data.valor_venta_disponible);
        } catch (e) {
            console.error('Error cargando métricas:', e);
        }
    }

    function renderStockList() {
        const query = norm($('stock-search').value);
        const visible = allProducts.filter(p => norm(p.nombre).includes(query));
        const listEl = $('stock-list');

        if (!visible.length) {
            listEl.innerHTML = '<div class="empty">No se encontraron productos en el inventario.</div>';
            return;
        }

        listEl.innerHTML = visible.map(p => {
            const isLow = p.stock_total <= p.stock_minimo;
            const isZero = p.stock_total === 0;
            const barWidth = Math.min(100, Math.round((p.stock_total / (p.stock_minimo * 4 || 10)) * 100));

            let estadoTexto = 'Disponible';
            if (isZero) {
                estadoTexto = 'Agotado';
            } else if (isLow) {
                estadoTexto = 'Reponer';
            }

            return `
                <div class="row" style="align-items: center; padding: 10px 0; border-bottom: 1px solid var(--line);">
                    <div style="flex: 1; padding-right: 10px;">
                        <b class="product-title-wrap" style="display: block;">${esc(p.nombre)}</b>
                        <small style="display: block; color: var(--muted); margin-top: 3px;">
                            ${p.stock_total} unidades disponibles · mínimo de alerta: ${p.stock_minimo} · Precio: Bs ${fmt(p.ultimo_precio)}
                        </small>
                        <div class="track" style="margin-top: 6px;">
                            <div class="bar ${isLow ? 'warnbar' : ''}" style="width: ${barWidth}%"></div>
                        </div>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap; justify-content: flex-end;">
                        <span class="pill ${isLow ? 'warn' : ''}">${estadoTexto}</span>
                        ${p.activo ? 
                            `<button type="button" class="link" data-retire-prod="${p.id}" style="color: #6a2cd8; font-size: .78rem;" title="Retirar del catálogo activo">
                                Archivar
                            </button>` : 
                            `<button type="button" class="link" data-reactivate-prod="${p.id}" style="color: #2b5c4f; font-size: .78rem;" title="Reactivar en catálogo activo">
                                Reactivar
                            </button>`
                        }
                        <button type="button" class="link" data-delete-prod="${p.id}" style="color: #b3382c; font-size: .78rem;" title="Eliminar producto y sus existencias">
                            Borrar
                        </button>
                    </div>
                </div>
            `;
        }).join('');
    }

    $('stock-search').oninput = renderStockList;

    $('stock-list').onclick = async e => {
        const retBtn = e.target.closest('[data-retire-prod]');
        if (retBtn) {
            const id = Number(retBtn.dataset.retireProd);
            const p = allProducts.find(x => x.id === id);
            if (!p || !confirm(`¿Deseas archivar "${p.nombre}" para retirarlo del catálogo activo?`)) return;
            try {
                const res = await fetch('/api/productos/', {
                    method: 'POST',
                    headers: getHeaders(),
                    body: JSON.stringify({ accion: 'retirar', producto_id: id })
                });
                const data = await res.json();
                info(data.mensaje || data.error);
                await loadProducts();
                await loadLots();
                await loadInventoryMetrics();
            } catch (err) {
                console.error('Error al archivar producto:', err);
            }
            return;
        }

        const reactBtn = e.target.closest('[data-reactivate-prod]');
        if (reactBtn) {
            const id = Number(reactBtn.dataset.reactivateProd);
            try {
                const res = await fetch('/api/productos/', {
                    method: 'POST',
                    headers: getHeaders(),
                    body: JSON.stringify({ accion: 'reactivar', producto_id: id })
                });
                const data = await res.json();
                info(data.mensaje || data.error);
                await loadProducts();
                await loadLots();
                await loadInventoryMetrics();
            } catch (err) {
                console.error('Error al reactivar producto:', err);
            }
            return;
        }

        const delBtn = e.target.closest('[data-delete-prod]');
        if (delBtn) {
            const id = Number(delBtn.dataset.deleteProd);
            const p = allProducts.find(x => x.id === id);
            if (!p) return;

            if (!confirm(`¿Estás seguro de eliminar "${p.nombre}" y todas sus existencias?`)) return;

            try {
                const res = await fetch('/api/productos/', {
                    method: 'POST',
                    headers: getHeaders(),
                    body: JSON.stringify({ accion: 'eliminar_total', producto_id: id })
                });
                const data = await res.json();
                if (res.ok) {
                    info(data.mensaje);
                    await loadProducts();
                    await loadEntries(1);
                    await loadLots();
                    await loadInventoryMetrics();
                } else if (data.puede_forzar) {
                    if (confirm(`${data.mensaje || data.error}\n\n¿Deseas forzar la eliminación de este producto y limpiar sus registros de prueba asociados?`)) {
                        const res2 = await fetch('/api/productos/', {
                            method: 'POST',
                            headers: getHeaders(),
                            body: JSON.stringify({ accion: 'eliminar_total', producto_id: id, forzar: true })
                        });
                        const data2 = await res2.json();
                        if (res2.ok) {
                            info(data2.mensaje);
                            await loadProducts();
                            await loadEntries(1);
                            await loadLots();
                            await loadInventoryMetrics();
                        } else {
                            info(data2.error || 'No se pudo forzar la eliminación.', true);
                        }
                    }
                } else {
                    info(data.error || 'No se pudo eliminar el producto.', true);
                }
            } catch (err) {
                console.error('Error al eliminar producto:', err);
            }
        }
    };

    // -------------------------------------------------------------------------
    // 04 · CONTROL DE GASTOS Y RETIROS (IDEMPOTENCIA ANTI-DUPLICADOS)
    // -------------------------------------------------------------------------
    async function loadExpenses() {
        const from = $('from-date') ? $('from-date').value : '';
        const to = $('to-date') ? $('to-date').value : '';
        let url = '/api/gastos/?';
        if (from) url += `desde=${encodeURIComponent(from)}&`;
        if (to) url += `hasta=${encodeURIComponent(to)}`;

        try {
            const res = await fetch(url);
            const data = await res.json();

            if ($('expense-store-total')) $('expense-store-total').textContent = 'Bs ' + fmt(data.total_tienda_bs);
            if ($('expense-owner-total')) $('expense-owner-total').textContent = 'Bs ' + fmt(data.total_personal_bs);
            if ($('expense-total-metric')) $('expense-total-metric').textContent = 'Bs ' + fmt(data.total_general_bs);
            if ($('expense-count')) $('expense-count').textContent = data.num_gastos || 0;

            const listEl = $('expense-list');
            if (!listEl) return;

            if (!data.gastos || !data.gastos.length) {
                listEl.innerHTML = '<div class="empty">No hay gastos ni retiros registrados en este período.</div>';
                return;
            }

            listEl.innerHTML = data.gastos.map(g => {
                const isPersonal = g.categoria === 'PERSONAL';
                return `
                    <div class="row" style="padding: 10px 0; border-bottom: 1px solid var(--line);">
                        <div>
                            <b>${esc(g.descripcion)}</b>
                            <span class="pill ${isPersonal ? 'warn' : ''}" style="margin-left: 6px; font-size: .7rem; ${isPersonal ? 'background: #f3e8ff; color: #6b21a8;' : ''}">
                                ${isPersonal ? 'Personal / Dueño' : 'Tienda / Operativo'}
                            </span>
                            <small style="display: block; color: var(--muted); margin-top: 2px;">
                                ${esc(g.fecha)} · Pagado vía ${esc(g.metodo_label)}${g.comprobante ? ` (Ref: ${esc(g.comprobante)})` : ''}
                            </small>
                            ${g.observaciones ? `<small class="muted" style="display: block; font-style: italic;">${esc(g.observaciones)}</small>` : ''}
                        </div>
                        <div style="text-align: right; display: flex; align-items: center; gap: 10px;">
                            <div>
                                <span class="amount" style="color: #b3382c;">Bs ${fmt(g.monto_equivalente_bs)}</span>
                                ${g.moneda !== 'BS' ? `<small class="muted" style="display:block;">${g.moneda} ${fmt(g.monto_original)}</small>` : ''}
                            </div>
                            <button type="button" class="link" data-delete-expense="${g.id}" style="color: #b3382c; font-size: .78rem;" title="Eliminar gasto">
                                Borrar
                            </button>
                        </div>
                    </div>
                `;
            }).join('');
        } catch (e) {
            console.error('Error cargando gastos:', e);
        }
    }

    if ($('expense-currency')) {
        $('expense-currency').onchange = () => {
            const curr = $('expense-currency').value;
            if (curr === 'USD') {
                $('expense-rate').value = $('rate-usd').value;
                $('expense-method').value = 'EFECTIVO_USD';
            } else if (curr === 'USDT') {
                $('expense-rate').value = $('rate-usdt').value;
                $('expense-method').value = 'USDT';
            } else {
                $('expense-rate').value = '1.00';
                $('expense-method').value = 'EFECTIVO_BS';
            }
        };
    }

    if ($('btn-save-expense')) {
        $('btn-save-expense').onclick = async () => {
            const desc = $('expense-desc').value.trim();
            const cat = $('expense-cat').value;
            const currency = $('expense-currency').value;
            const amount = parseMoney($('expense-amount').value);
            const method = $('expense-method').value;
            const ref = $('expense-ref').value.trim();
            const rate = parseMoney($('expense-rate').value) || 1.0;
            const notes = $('expense-notes').value.trim();

            if (!desc) {
                info('Indica la descripción o motivo del gasto.', true);
                $('expense-desc').focus();
                return;
            }

            if (amount <= 0) {
                info('El monto del gasto debe ser mayor a cero.', true);
                $('expense-amount').focus();
                return;
            }

            $('btn-save-expense').disabled = true;
            $('btn-save-expense').textContent = 'Guardando egreso...';

            const expenseToken = (window.crypto && crypto.randomUUID) 
                ? crypto.randomUUID() 
                : ('EXP-' + Date.now() + '-' + Math.random().toString(36).substring(2, 9));

            try {
                const res = await fetch('/api/gastos/', {
                    method: 'POST',
                    headers: getHeaders(),
                    body: JSON.stringify({
                        descripcion: desc,
                        categoria: cat,
                        moneda: currency,
                        monto: amount,
                        metodo: method,
                        tasa: rate,
                        comprobante: ref,
                        observaciones: notes,
                        idempotency_key: expenseToken
                    })
                });
                const data = await res.json();
                if (res.ok) {
                    info(data.mensaje);
                    $('expense-desc').value = '';
                    $('expense-amount').value = '';
                    $('expense-ref').value = '';
                    $('expense-notes').value = '';
                    await loadExpenses();
                    await loadReport();
                } else {
                    info(data.error || 'Error al guardar el gasto.', true);
                }
            } catch (e) {
                console.error('Error al registrar gasto:', e);
                info('Error de red al intentar registrar el gasto.', true);
            } finally {
                $('btn-save-expense').disabled = false;
                $('btn-save-expense').textContent = 'Registrar gasto / salida';
            }
        };
    }

    if ($('expense-list')) {
        $('expense-list').onclick = async e => {
            const delBtn = e.target.closest('[data-delete-expense]');
            if (delBtn) {
                const id = Number(delBtn.dataset.deleteExpense);
                if (!confirm('¿Estás seguro de eliminar este registro de gasto?')) return;

                try {
                    const res = await fetch(`/api/gastos/${id}/eliminar/`, {
                        method: 'POST',
                        headers: getHeaders()
                    });
                    const data = await res.json();
                    if (res.ok) {
                        info(data.mensaje);
                        await loadExpenses();
                        await loadReport();
                    } else {
                        info(data.error || 'No se pudo eliminar el gasto.', true);
                    }
                } catch (err) {
                    console.error('Error al eliminar gasto:', err);
                    info('Error de red al eliminar el gasto.', true);
                }
            }
        };
    }

    // -------------------------------------------------------------------------
    // 05 · ANÁLISIS Y REPORTES (RESUMEN DEL PERÍODO + INVENTARIO ACTUAL)
    // -------------------------------------------------------------------------
    async function loadReport() {
        const from = $('from-date').value;
        const to = $('to-date').value;
        let url = '/api/reportes/resumen/?';
        if (from) url += `desde=${encodeURIComponent(from)}&`;
        if (to) url += `hasta=${encodeURIComponent(to)}`;

        let excelUrl = '/reportes/excel/?';
        if (from) excelUrl += `desde=${encodeURIComponent(from)}&`;
        if (to) excelUrl += `hasta=${encodeURIComponent(to)}`;
        if ($('download-report-excel')) $('download-report-excel').href = excelUrl;
        if ($('download-stock-excel')) $('download-stock-excel').href = excelUrl;

        try {
            const res = await fetch(url);
            const data = await res.json();

            // Bloque A · Métricas del período
            if ($('sold-count')) $('sold-count').textContent = data.total_unidades_vendidas || 0;
            if ($('sales-value')) $('sales-value').textContent = 'Bs ' + fmt(data.total_ingresos);
            if ($('cost-value')) $('cost-value').textContent = 'Bs ' + fmt(data.total_costos || 0);
            if ($('profit-value')) $('profit-value').textContent = 'Bs ' + fmt(data.total_ganancia);
            if ($('expenses-store-metric')) $('expenses-store-metric').textContent = 'Bs ' + fmt(data.total_gastos_tienda || 0);
            if ($('net-profit-value')) $('net-profit-value').textContent = 'Bs ' + fmt(data.resultado_despues_gastos || data.ganancia_neta_real || 0);
            if ($('expenses-personal-metric')) $('expenses-personal-metric').textContent = 'Bs ' + fmt(data.total_gastos_personal || 0);

            if ($('period-info')) $('period-info').textContent = `${data.num_ventas} venta(s) registradas en este período.`;

            // Bloque B · Inventario actual a la fecha de consulta
            if (data.inventario_actual) {
                if ($('inv-consult-date')) $('inv-consult-date').textContent = `Al corte de: ${data.inventario_actual.fecha_consulta}`;
                if ($('inv-active-prods')) $('inv-active-prods').textContent = data.inventario_actual.total_productos_activos || 0;
                if ($('inv-total-units')) $('inv-total-units').textContent = data.inventario_actual.unidades_disponibles || 0;
                if ($('inv-cost-value')) $('inv-cost-value').textContent = 'Bs ' + fmt(data.inventario_actual.inversion_existencias || 0);
                if ($('inv-potential-sale')) $('inv-potential-sale').textContent = 'Bs ' + fmt(data.inventario_actual.venta_potencial || 0);
            }

            // Productos vendidos
            const soldEl = $('sold-products');
            if (soldEl) {
                if (!data.productos_vendidos.length) {
                    soldEl.innerHTML = '<div class="empty">No hubo ventas de productos en este período.</div>';
                } else {
                    soldEl.innerHTML = data.productos_vendidos.map(p => `
                        <div class="row" style="padding: 8px 0; border-bottom: 1px solid var(--line);">
                            <div>
                                <b class="product-title-wrap" style="display: block;">${esc(p.nombre)}</b>
                                <small>${p.unidades} unidades · Ventas: Bs ${fmt(p.ingresos)}</small>
                            </div>
                            <div style="text-align: right;">
                                <span class="amount" style="color: #376d5e;">Ganancia: Bs ${fmt(p.ganancia)}</span>
                                <small class="muted" style="display: block;">Costo: Bs ${fmt(p.costo)}</small>
                            </div>
                        </div>
                    `).join('');
                }
            }

            // Cobros por medio (recibido, vuelto y neto)
            const payEl = $('payment-totals');
            if (payEl) {
                if (!data.cobros_por_medio.length) {
                    payEl.innerHTML = '<div class="empty">Sin pagos registrados en este período.</div>';
                } else {
                    payEl.innerHTML = data.cobros_por_medio.map(c => `
                        <div class="row" style="padding: 8px 0; border-bottom: 1px solid var(--line);">
                            <div>
                                <b>${esc(c.metodo)}</b>
                                <small style="display: block;">${c.transacciones} operaciones · Recibido: ${esc(c.moneda)} ${fmt(c.monto_recibido || c.total_original)}</small>
                                ${(c.vuelto_entregado_bs > 0) ? `<small style="color: #b3382c; display: block;">Vuelto entregado: Bs ${fmt(c.vuelto_entregado_bs)}</small>` : ''}
                            </div>
                            <div style="text-align: right;">
                                <span class="amount">Neto: Bs ${fmt(c.total_bs)}</span>
                                <small class="muted" style="display: block;">${esc(c.moneda)} ${fmt(c.total_original)}</small>
                            </div>
                        </div>
                    `).join('');
                }
            }

            // Productos por reponer (solo alertas de stock)
            const alertEl = $('short-list');
            if (alertEl) {
                if (!data.productos_alerta.length) {
                    alertEl.innerHTML = '<div class="empty">Todo el inventario se encuentra en niveles normales.</div>';
                } else {
                    alertEl.innerHTML = data.productos_alerta.map(p => `
                        <div class="row">
                            <div>
                                <b class="product-title-wrap" style="display: block;">${esc(p.nombre)}</b>
                                <small>Quedan ${p.stock_actual} uds · mínimo de aviso: ${p.stock_minimo}</small>
                            </div>
                            <span class="pill warn">${p.estado === 'agotado' ? 'Agotado' : 'Reponer'}</span>
                        </div>
                    `).join('');
                }
            }

            // Detalle de ventas con soporte de anulación
            const logEl = $('sales-log');
            if (logEl) {
                if (!data.ventas.length) {
                    logEl.innerHTML = '<div class="empty">No hay ventas para el período seleccionado.</div>';
                } else {
                    logEl.innerHTML = data.ventas.map(v => `
                        <div class="row" style="${v.anulada ? 'opacity: 0.6; background: #fff5f5;' : ''}; padding: 10px 0; border-bottom: 1px solid var(--line);">
                            <div>
                                <b>${esc(v.codigo)}</b> · <span class="muted">${esc(v.fecha)}</span>
                                ${v.anulada ? '<span style="background: #fde8e8; color: #9b1c1c; font-size: .7rem; padding: 2px 6px; border-radius: 4px; font-weight: bold; margin-left: 6px;">ANULADA</span>' : ''}
                                <small style="display: block; margin-top: 3px;">Artículos: ${esc(v.articulos)}</small>
                                <small style="display: block; color: var(--muted);">Pagos: ${esc(v.medios)}${v.vuelto_total_bs > 0 ? ` · Vuelto: Bs ${fmt(v.vuelto_total_bs)}` : ''}</small>
                                ${!v.anulada ? `
                                    <button type="button" class="link" onclick="window.anularVenta('${esc(v.codigo)}')" style="color: #b3382c; font-size: .75rem; padding: 0; margin-top: 4px;">
                                        ✕ Anular venta y devolver existencias
                                    </button>
                                ` : ''}
                            </div>
                            <div style="text-align: right;">
                                <span class="amount">Bs ${fmt(v.total_bs)}</span>
                                <small style="display: block; color: #376d5e;">Ganancia: Bs ${fmt(v.ganancia_bruta_bs)}</small>
                            </div>
                        </div>
                    `).join('');
                }
            }

        } catch (e) {
            console.error('Error cargando reporte:', e);
        }
    }

    // Botones rápidos de período
    document.querySelectorAll('[data-period]').forEach(btn => {
        btn.onclick = () => {
            const p = btn.dataset.period;
            const caracasNow = new Date(new Date().toLocaleString("en-US", { timeZone: "America/Caracas" }));
            const pad = n => String(n).padStart(2, '0');
            const toStr = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

            const today = toStr(caracasNow);
            $('to-date').value = today;

            if (p === 'all') {
                $('from-date').value = '';
                $('to-date').value = '';
            } else if (p === 'today') {
                $('from-date').value = today;
            } else if (p === 'week') {
                const past = new Date(caracasNow);
                past.setDate(past.getDate() - 6);
                $('from-date').value = toStr(past);
            } else if (p === 'half') {
                const day = caracasNow.getDate();
                const past = new Date(caracasNow);
                if (day > 15) {
                    past.setDate(16);
                } else {
                    past.setDate(1);
                }
                $('from-date').value = toStr(past);
            } else if (p === 'month') {
                const past = new Date(caracasNow.getFullYear(), caracasNow.getMonth(), 1);
                $('from-date').value = toStr(past);
            }
            void loadReport();
        };
    });

    $('from-date').onchange = () => { void loadReport(); };
    $('to-date').onchange = () => { void loadReport(); };

    // -------------------------------------------------------------------------
    // RESTAURACIÓN DE COPIAS DE SEGURIDAD (.JSON O .XLSX) SIN COMANDOS
    // -------------------------------------------------------------------------
    const restoreFileInput = $('global-restore-file');

    function triggerRestoreDialog() {
        if (restoreFileInput) restoreFileInput.click();
    }

    if ($('btn-restore-header')) $('btn-restore-header').onclick = triggerRestoreDialog;
    if ($('btn-restore-tab4')) $('btn-restore-tab4').onclick = triggerRestoreDialog;

    if (restoreFileInput) {
        restoreFileInput.onchange = async () => {
            const file = restoreFileInput.files?.[0];
            if (!file) return;

            const filename = file.name;
            const isJson = filename.toLowerCase().endsWith('.json');
            const isXlsx = filename.toLowerCase().endsWith('.xlsx');

            if (!isJson && !isXlsx) {
                info('Por favor selecciona un archivo de respaldo válido (.json o .xlsx).', true);
                restoreFileInput.value = '';
                return;
            }

            const promptMsg = isJson 
                ? `¿Estás seguro de restaurar la base de datos completa desde "${filename}"?\n\nSe recuperarán productos, existencias y ventas anteriores.` 
                : `¿Deseas importar/recuperar productos y existencias desde el archivo Excel "${filename}"?`;

            if (!confirm(promptMsg)) {
                restoreFileInput.value = '';
                return;
            }

            info(`Restaurando "${filename}", por favor espera unos segundos...`);
            const formData = new FormData();
            formData.append('archivo', file);

            try {
                const res = await fetch('/api/reportes/restaurar/', {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': window.CSRF_TOKEN || ''
                    },
                    body: formData
                });
                const data = await res.json();
                if (res.ok && data.exito) {
                    info(data.mensaje);
                    await Promise.all([
                        loadProducts(),
                        loadEntries(1),
                        loadLots(),
                        loadInventoryMetrics(),
                        loadReport()
                    ]);
                } else {
                    info(data.error || 'No se pudo procesar la restauración del archivo.', true);
                }
            } catch (err) {
                console.error('Error al restaurar archivo:', err);
                info('Error de red al intentar restaurar el archivo.', true);
            } finally {
                restoreFileInput.value = '';
            }
        };
    }

    // Función global para anular venta y reincorporar inventario
    window.anularVenta = async (codigo) => {
        if (!confirm(`¿Estás seguro de anular la venta "${codigo}"?\nLas existencias vendidas serán devueltas a sus lotes correspondientes y el total se descontará de los reportes.`)) {
            return;
        }
        try {
            const res = await fetch(`/api/ventas/${encodeURIComponent(codigo)}/anular/`, {
                method: 'POST',
                headers: getHeaders(),
                body: JSON.stringify({ motivo: 'Anulación solicitada desde interfaz' })
            });
            const data = await res.json();
            if (res.ok && data.exito) {
                info(data.mensaje);
                await Promise.all([
                    loadProducts(),
                    loadLots(),
                    loadInventoryMetrics(),
                    loadReport()
                ]);
            } else {
                info(data.error || 'No se pudo anular la venta.', true);
            }
        } catch (err) {
            console.error('Error al anular venta:', err);
            info('Error de conexión al intentar anular la venta.', true);
        }
    };

    // -------------------------------------------------------------------------
    // INICIALIZACIÓN EN PARALELO
    // -------------------------------------------------------------------------
    Promise.all([
        loadRates(),
        loadProducts(),
        loadEntries(1),
        loadLots(),
        loadInventoryMetrics(),
        loadExpenses()
    ]).catch(err => console.error('Error inicializando:', err));

})
    // -------------------------------------------------------------------------
    // 06 · REINICIO DE DATOS Y LIMPIEZA DE PRUEBAS
    // -------------------------------------------------------------------------
    if ($('btn-reset-sales-only')) {
        $('btn-reset-sales-only').onclick = async () => {
            if (!confirm('¿Estás seguro de limpiar todas las ventas y gastos de prueba?\n\nEsta acción restaurará el stock de tus entradas al 100% de lo recibido y dejará las ventas en 0.')) return;
            try {
                const res = await fetch('/api/sistema/reiniciar/', {
                    method: 'POST',
                    headers: getHeaders(),
                    body: JSON.stringify({ modo: 'solo_ventas_gastos' })
                });
                const data = await res.json();
                if (res.ok) {
                    info(data.mensaje);
                    await loadProducts();
                    await loadEntries(1);
                    await loadLots();
                    await loadExpenses();
                    await loadInventoryMetrics();
                    await loadReport();
                } else {
                    info(data.error || 'Error al reiniciar ventas.', true);
                }
            } catch (e) {
                console.error(e);
            }
        };
    }

    if ($('btn-reset-all-zero')) {
        $('btn-reset-all-zero').onclick = async () => {
            const resp = prompt('⚠️ ATENCIÓN: Esta opción eliminará TODOS los productos, entradas, ventas y gastos para empezar de 0.\n\nEscribe "BORRAR TODO" para confirmar:');
            if (resp !== 'BORRAR TODO') {
                if (resp !== null) alert('Confirmación incorrecta. No se realizaron cambios.');
                return;
            }
            try {
                const res = await fetch('/api/sistema/reiniciar/', {
                    method: 'POST',
                    headers: getHeaders(),
                    body: JSON.stringify({ modo: 'todo_a_cero' })
                });
                const data = await res.json();
                if (res.ok) {
                    info(data.mensaje);
                    await loadProducts();
                    await loadEntries(1);
                    await loadLots();
                    await loadExpenses();
                    await loadInventoryMetrics();
                    await loadReport();
                } else {
                    info(data.error || 'Error al reiniciar todo.', true);
                }
            } catch (e) {
                console.error(e);
            }
        };
    }
})();
