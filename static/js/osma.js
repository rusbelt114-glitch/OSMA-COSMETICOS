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
    let availableLots = [];
    let cart = [];
    let selectedProductId = null;

    // Mensaje de notificación
    function info(msg, isError = false) {
        const el = $('notice');
        el.textContent = msg;
        el.className = 'notice ' + (isError ? 'error' : '');
        if (msg) {
            clearTimeout(window._noticeTimer);
            window._noticeTimer = setTimeout(() => { el.textContent = ''; }, 6000);
        }
    }

    // Cabecera CSRF para Django
    function getHeaders() {
        return {
            'Content-Type': 'application/json',
            'X-CSRFToken': window.CSRF_TOKEN || ''
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
            ['entry', 'sell', 'stock', 'refill'].forEach(id => {
                const el = $(id);
                if (el) el.hidden = (id !== tab);
            });
            if (tab === 'stock') void loadInventoryMetrics();
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
                $('bar-usd-rate').textContent = 'Bs ' + fmt(data.usd_bcv);
                $('rate-usd').value = data.usd_bcv.toFixed(2).replace('.', ',');
            }
            if (data.usdt) {
                $('bar-usdt-rate').textContent = 'Bs ' + fmt(data.usdt);
                $('rate-usdt').value = data.usdt.toFixed(2).replace('.', ',');
            }
            if (data.fecha_actualizacion) {
                $('rates-updated-text').textContent = 'Actualizado: ' + data.fecha_actualizacion;
            }
            updatePaymentCalculations();
        } catch (e) {
            console.error('Error cargando tasas:', e);
        }
    }

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
    // 01 · ENTRADA DE PRODUCTOS
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

    async function loadEntries() {
        try {
            const res = await fetch('/api/entradas/');
            const data = await res.json();
            recentEntries = data.entradas || [];
            renderRecentEntries();
        } catch (e) {
            console.error('Error cargando entradas:', e);
        }
    }

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
                    precio_venta: precio_venta
                })
            });
            const data = await res.json();
            if (!res.ok) {
                info(data.error || 'Error al guardar entrada.', true);
            } else {
                info(data.mensaje);
                resetEntryForm();
                await Promise.all([
                    loadProducts(),
                    loadEntries(),
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

    function renderRecentEntries() {
        const el = $('recent-entries');
        if (!recentEntries.length) {
            el.innerHTML = '<div class="empty">Las entradas que registres aparecerán aquí.</div>';
            return;
        }
        el.innerHTML = recentEntries.slice(0, 10).map(e => `
            <div class="row">
                <div>
                    <b>${esc(e.producto_nombre)}</b>
                    <small>${esc(e.fecha)} · ${e.cantidad_recibida} uds recibidas (${e.cantidad_disponible} disp.)</small>
                    <button type="button" class="link" data-delete-entry="${e.id}" style="color: #b3382c; font-size: .75rem; padding: 0; margin-top: 4px;">
                        ✕ Anular esta entrada
                    </button>
                </div>
                <div style="text-align: right;">
                    <span class="amount">Bs ${fmt(e.precio_venta)}</span>
                    <small class="muted">Costo: Bs ${fmt(e.costo_unitario)}</small>
                </div>
            </div>
        `).join('');
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
                    loadEntries(),
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
    // 02 · VENTAS Y PUNTO DE COBRO MULTI-MONEDA (POR LOTE O PRECIO PERSONALIZADO)
    // -------------------------------------------------------------------------
    async function loadLots() {
        try {
            const res = await fetch('/api/lotes/disponibles/');
            const data = await res.json();
            availableLots = data.lotes || [];
            renderSellProductChoices();
        } catch (e) {
            console.error('Error cargando lotes:', e);
        }
    }

    function renderSellProductChoices() {
        const query = norm($('sell-search').value);
        const select = $('sell-product-select');

        const productosConStock = allProducts.filter(p => p.stock_total > 0 && norm(p.nombre).includes(query));

        if (!productosConStock.length && !availableLots.length) {
            select.innerHTML = '<option value="">No hay productos con existencias disponibles</option>';
            $('add-cart').disabled = true;
            $('sell-unit-price').value = '0,00';
            return;
        }

        let html = '';
        productosConStock.forEach(p => {
            const lotesDelProd = availableLots.filter(l => l.producto_id === p.id && l.cantidad_disponible > 0);
            
            // Opción principal: FIFO Automático sobre todo el inventario del producto
            html += `<option value="prod_${p.id}" data-type="prod" data-id="${p.id}" data-price="${p.ultimo_precio}" data-stock="${p.stock_total}">
                ${esc(p.nombre)} · ${p.stock_total} disp. · Bs ${fmt(p.ultimo_precio)} (FIFO Automático)
            </option>`;

            // Opciones secundarias: si tiene varios lotes y el dueño prefiere vender de un lote específico
            if (lotesDelProd.length > 1) {
                lotesDelProd.forEach(l => {
                    html += `<option value="lote_${l.lote_id}" data-type="lote" data-id="${l.lote_id}" data-prod-id="${p.id}" data-price="${l.precio_venta}" data-stock="${l.cantidad_disponible}">
                        &nbsp;&nbsp;&nbsp;&nbsp;↳ Lote entrada ${esc(l.fecha)} · ${l.cantidad_disponible} disp. · Bs ${fmt(l.precio_venta)}
                    </option>`;
                });
            }
        });

        if (!html && availableLots.length) {
            availableLots.filter(l => norm(l.producto_nombre).includes(query)).forEach(l => {
                html += `<option value="lote_${l.lote_id}" data-type="lote" data-id="${l.lote_id}" data-prod-id="${l.producto_id}" data-price="${l.precio_venta}" data-stock="${l.cantidad_disponible}">
                    ${esc(l.producto_nombre)} · ${l.cantidad_disponible} disp. · Bs ${fmt(l.precio_venta)} (Lote ${esc(l.fecha)})
                </option>`;
            });
        }

        if (!html) {
            select.innerHTML = '<option value="">No hay productos con existencias disponibles</option>';
            $('add-cart').disabled = true;
            $('sell-unit-price').value = '0,00';
            return;
        }

        select.innerHTML = html;
        $('add-cart').disabled = false;
        updateSelectedProductPrice();
    }

    function updateSelectedProductPrice() {
        const select = $('sell-product-select');
        const opt = select.options[select.selectedIndex];
        if (opt && opt.dataset.price) {
            $('sell-unit-price').value = Number.parseFloat(opt.dataset.price).toFixed(2).replace('.', ',');
        }
    }

    $('sell-search').oninput = renderSellProductChoices;
    $('sell-product-select').onchange = updateSelectedProductPrice;

    function _agregarLoteAlCarrito(loteId, qty, unitPrice, prodId) {
        const lote = availableLots.find(x => x.lote_id === loteId);
        if (!lote) {
            info('Lote no encontrado.', true);
            return false;
        }
        const existing = cart.find(item => item.lote_id === loteId);
        const totalQtyNeeded = (existing ? existing.cantidad : 0) + qty;
        if (totalQtyNeeded > lote.cantidad_disponible) {
            info(`Solo hay ${lote.cantidad_disponible} unidades disponibles en este lote.`, true);
            return false;
        }

        if (existing) {
            existing.cantidad += qty;
            existing.precio_unitario_bs = unitPrice;
        } else {
            cart.push({
                lote_id: loteId,
                producto_id: prodId,
                nombre: `${lote.producto_nombre} (Lote ${lote.fecha})`,
                cantidad: qty,
                precio_unitario_bs: unitPrice
            });
        }
        info(`Agregado a la venta: ${lote.producto_nombre} a Bs ${fmt(unitPrice)}.`);
        return true;
    }

    function _agregarProductoAlCarrito(prodId, qty, unitPrice) {
        const prod = allProducts.find(x => x.id === prodId);
        if (!prod) {
            info('Producto no encontrado.', true);
            return false;
        }
        const existing = cart.find(item => item.producto_id === prodId && !item.lote_id);
        const totalQtyNeeded = (existing ? existing.cantidad : 0) + qty;
        if (totalQtyNeeded > prod.stock_total) {
            info(`Solo hay ${prod.stock_total} unidades disponibles en total para "${prod.nombre}".`, true);
            return false;
        }

        if (existing) {
            existing.cantidad += qty;
            existing.precio_unitario_bs = unitPrice;
        } else {
            cart.push({
                producto_id: prodId,
                nombre: prod.nombre,
                cantidad: qty,
                precio_unitario_bs: unitPrice
            });
        }
        info(`Agregado a la venta: ${prod.nombre} a Bs ${fmt(unitPrice)}.`);
        return true;
    }

    $('add-cart').onclick = () => {
        const select = $('sell-product-select');
        const opt = select.options[select.selectedIndex];
        if (!opt?.value) return;

        const qty = Number.parseInt($('units').value, 10);
        const unitPrice = parseMoney($('sell-unit-price').value);

        if (Number.isNaN(qty) || qty <= 0) {
            info('Por favor indica una cantidad mayor a 0.', true);
            $('units').focus();
            return;
        }
        if (unitPrice <= 0) {
            info('El precio de venta debe ser mayor a 0.', true);
            $('sell-unit-price').focus();
            return;
        }

        const id = Number(opt.dataset.id);
        const type = opt.dataset.type;
        const agregado = (type === 'lote')
            ? _agregarLoteAlCarrito(id, qty, unitPrice, Number(opt.dataset.prodId))
            : _agregarProductoAlCarrito(id, qty, unitPrice);

        if (agregado) {
            $('units').value = '1';
            renderCart();
        }
    };

    function renderCart() {
        const cartEl = $('cart');
        if (!cart.length) {
            cartEl.innerHTML = '<div class="empty">Aún no hay productos en esta venta.</div>';
            $('finish').disabled = true;
            $('sale-total').textContent = 'Bs 0,00';
            updatePaymentCalculations();
            return;
        }

        cartEl.innerHTML = cart.map((item, idx) => `
            <div class="row">
                <div>
                    <b>${esc(item.nombre)}</b>
                    <small>${item.cantidad} × Bs ${fmt(item.precio_unitario_bs)}</small>
                </div>
                <div style="display: flex; align-items: center; gap: 12px;">
                    <span class="amount">Bs ${fmt(item.cantidad * item.precio_unitario_bs)}</span>
                    <button type="button" class="link" data-remove-cart="${idx}" style="color: #b3382c;">Quitar</button>
                </div>
            </div>
        `).join('');

        const total = cart.reduce((acc, i) => acc + (i.cantidad * i.precio_unitario_bs), 0);
        $('sale-total').textContent = 'Bs ' + fmt(total);
        $('finish').disabled = false;
        updatePaymentCalculations();
    }

    $('cart').onclick = e => {
        const btn = e.target.closest('[data-remove-cart]');
        if (!btn) return;
        const idx = Number(btn.dataset.removeCart);
        cart.splice(idx, 1);
        renderCart();
    };

    function updatePaymentCalculations() {
        const totalSale = cart.reduce((acc, i) => acc + (i.cantidad * i.precio_unitario_bs), 0);
        const payBs = parseMoney($('pay-bs').value);
        const payMobile = parseMoney($('pay-mobile').value);
        const payUsd = parseMoney($('pay-usd').value);
        const payUsdt = parseMoney($('pay-usdt').value);

        const rateUsd = parseMoney($('rate-usd').value);
        const rateUsdt = parseMoney($('rate-usdt').value);

        const equivUsd = payUsd * rateUsd;
        const equivUsdt = payUsdt * rateUsdt;
        const totalPaid = payBs + payMobile + equivUsd + equivUsdt;

        const diff = totalSale - totalPaid;
        const convEl = $('conversion');

        if (totalPaid === 0 && totalSale === 0) {
            convEl.textContent = '';
            return;
        }

        let txt = `Total recibido: Bs ${fmt(totalPaid)}`;
        if (Math.abs(diff) < 0.05) {
            txt += ' · ¡Pago exacto!';
            convEl.style.color = '#376d5e';
        } else if (diff > 0) {
            txt += ` · Faltan Bs ${fmt(diff)}`;
            convEl.style.color = '#b3382c';
        } else {
            txt += ` · Cambio a entregar: Bs ${fmt(Math.abs(diff))}`;
            convEl.style.color = '#376d5e';
        }
        convEl.textContent = txt;
    }

    ['pay-bs', 'pay-mobile', 'pay-usd', 'pay-usdt', 'rate-usd', 'rate-usdt'].forEach(id => {
        $(id).oninput = updatePaymentCalculations;
    });

    $('finish').onclick = async () => {
        if (!cart.length) return;
        const totalSale = cart.reduce((acc, i) => acc + (i.cantidad * i.precio_unitario_bs), 0);

        const payBs = parseMoney($('pay-bs').value);
        const payMobile = parseMoney($('pay-mobile').value);
        const payUsd = parseMoney($('pay-usd').value);
        const payUsdt = parseMoney($('pay-usdt').value);

        const rateUsd = parseMoney($('rate-usd').value);
        const rateUsdt = parseMoney($('rate-usdt').value);

        const pagosList = [];
        if (payBs > 0) pagosList.push({ metodo: 'EFECTIVO_BS', monto_original: payBs });
        if (payMobile > 0) pagosList.push({ metodo: 'PAGO_MOVIL', monto_original: payMobile });
        if (payUsd > 0) {
            if (rateUsd <= 0) { info('Debes indicar una tasa válida para el pago en USD.', true); return; }
            pagosList.push({ metodo: 'EFECTIVO_USD', monto_original: payUsd });
        }
        if (payUsdt > 0) {
            if (rateUsdt <= 0) { info('Debes indicar una tasa válida para el pago en USDT.', true); return; }
            pagosList.push({ metodo: 'USDT', monto_original: payUsdt });
        }

        const totalPaid = payBs + payMobile + (payUsd * rateUsd) + (payUsdt * rateUsdt);
        if (totalPaid < (totalSale - 0.50)) {
            info(`El pago recibido (Bs ${fmt(totalPaid)}) es menor que el total (Bs ${fmt(totalSale)}).`, true);
            return;
        }

        $('finish').disabled = true;
        $('finish').textContent = 'Registrando venta...';

        try {
            const res = await fetch('/api/ventas/', {
                method: 'POST',
                headers: getHeaders(),
                body: JSON.stringify({
                    items: cart,
                    pagos: pagosList,
                    tasa_usd: rateUsd,
                    tasa_usdt: rateUsdt
                })
            });
            if (res.redirected || res.url.includes('/login/')) {
                info('La sesión de la tienda expiró. Redirigiendo al acceso...', true);
                setTimeout(() => { window.location.href = '/login/'; }, 1500);
                return;
            }
            const data = await res.json();
            if (!res.ok) {
                info(data.error || 'Error al procesar venta.', true);
            } else {
                info(data.mensaje);
                cart = [];
                renderCart();
                ['pay-bs', 'pay-mobile', 'pay-usd', 'pay-usdt'].forEach(id => { $(id).value = '0'; });
                updatePaymentCalculations();
                await loadProducts();
                await loadLots();
                await loadInventoryMetrics();
            }
        } catch (e) {
            console.error('Error venta:', e);
            info('Error al registrar la venta. Verifica montos o sesión.', true);
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
            $('product-count').textContent = data.total_productos || 0;
            $('stock-count').textContent = data.unidades_disponibles || 0;
            $('stock-value').textContent = 'Bs ' + fmt(data.valor_venta_disponible);
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
                <div class="row">
                    <div style="flex: 1;">
                        <b>${esc(p.nombre)}</b>
                        <small>${p.stock_total} unidades disponibles · mínimo de alerta: ${p.stock_minimo} · Precio: Bs ${fmt(p.ultimo_precio)}</small>
                        <div class="track">
                            <div class="bar ${isLow ? 'warnbar' : ''}" style="width: ${barWidth}%"></div>
                        </div>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap; justify-content: flex-end;">
                        <span class="pill ${isLow ? 'warn' : ''}">${estadoTexto}</span>
                        <button type="button" class="link" data-delete-prod="${p.id}" style="color: #b3382c; font-size: .78rem;" title="Eliminar producto y sus entradas">
                            Borrar
                        </button>
                    </div>
                </div>
            `;
        }).join('');
    }

    $('stock-search').oninput = renderStockList;

    $('stock-list').onclick = async e => {
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
                    await loadEntries();
                    await loadInventoryMetrics();
                } else {
                    info(data.error || 'No se pudo eliminar el producto.', true);
                }
            } catch (err) {
                console.error('Error al eliminar producto:', err);
                info('Error de red al intentar eliminar el producto.', true);
            }
        }
    };

    // -------------------------------------------------------------------------
    // 04 · ANÁLISIS, REPORTES Y GANANCIA BRUTA
    // -------------------------------------------------------------------------
    async function loadReport() {
        const from = $('from-date').value;
        const to = $('to-date').value;
        let url = '/api/reportes/resumen/?';
        if (from) url += `desde=${encodeURIComponent(from)}&`;
        if (to) url += `hasta=${encodeURIComponent(to)}`;

        // Actualizar link de descarga de Excel
        let excelUrl = '/reportes/excel/?';
        if (from) excelUrl += `desde=${encodeURIComponent(from)}&`;
        if (to) excelUrl += `hasta=${encodeURIComponent(to)}`;
        $('download-report-excel').href = excelUrl;
        $('download-stock-excel').href = excelUrl;

        try {
            const res = await fetch(url);
            const data = await res.json();

            $('sold-count').textContent = data.total_unidades_vendidas || 0;
            $('sales-value').textContent = 'Bs ' + fmt(data.total_ingresos);
            $('profit-value').textContent = 'Bs ' + fmt(data.total_ganancia);

            $('period-info').textContent = `${data.num_ventas} venta(s) registradas en este período.`;

            // Productos vendidos
            const soldEl = $('sold-products');
            if (!data.productos_vendidos.length) {
                soldEl.innerHTML = '<div class="empty">No hubo ventas de productos en este período.</div>';
            } else {
                soldEl.innerHTML = data.productos_vendidos.map(p => `
                    <div class="row">
                        <div>
                            <b>${esc(p.nombre)}</b>
                            <small>${p.unidades} unidades · Ventas: Bs ${fmt(p.ingresos)}</small>
                        </div>
                        <div style="text-align: right;">
                            <span class="amount" style="color: #376d5e;">Ganancia: Bs ${fmt(p.ganancia)}</span>
                            <small class="muted">Costo: Bs ${fmt(p.costo)}</small>
                        </div>
                    </div>
                `).join('');
            }

            // Cobros por medio
            const payEl = $('payment-totals');
            if (!data.cobros_por_medio.length) {
                payEl.innerHTML = '<div class="empty">Sin pagos registrados en este período.</div>';
            } else {
                payEl.innerHTML = data.cobros_por_medio.map(c => `
                    <div class="row">
                        <div>
                            <b>${esc(c.metodo)}</b>
                            <small>${c.transacciones} operaciones</small>
                        </div>
                        <div style="text-align: right;">
                            <span class="amount">${esc(c.moneda)} ${fmt(c.total_original)}</span>
                            <small class="muted">= Bs ${fmt(c.total_bs)}</small>
                        </div>
                    </div>
                `).join('');
            }

            // Productos por reponer
            const alertEl = $('short-list');
            if (!data.productos_alerta.length) {
                alertEl.innerHTML = '<div class="empty">Todo el inventario se encuentra en niveles normales.</div>';
            } else {
                alertEl.innerHTML = data.productos_alerta.map(p => `
                    <div class="row">
                        <div>
                            <b>${esc(p.nombre)}</b>
                            <small>Quedan ${p.stock_actual} uds · mínimo de aviso: ${p.stock_minimo}</small>
                        </div>
                        <span class="pill warn">${p.estado === 'agotado' ? 'Agotado' : 'Reponer'}</span>
                    </div>
                `).join('');
            }

            // Detalle de ventas
            const logEl = $('sales-log');
            if (!data.ventas.length) {
                logEl.innerHTML = '<div class="empty">No hay ventas para el período seleccionado.</div>';
            } else {
                logEl.innerHTML = data.ventas.map(v => `
                    <div class="row">
                        <div>
                            <b>${esc(v.codigo)}</b> · <span class="muted">${esc(v.fecha)}</span>
                            <small>${esc(v.articulos)}</small>
                            <small class="muted">Cobro: ${esc(v.medios)}</small>
                        </div>
                        <div style="text-align: right;">
                            <span class="amount">Bs ${fmt(v.total_bs)}</span>
                            <small style="color: #376d5e;">Ganancia: Bs ${fmt(v.ganancia_bruta_bs)}</small>
                        </div>
                    </div>
                `).join('');
            }

        } catch (e) {
            console.error('Error cargando reporte:', e);
        }
    }

    // Botones rápidos de período
    document.querySelectorAll('[data-period]').forEach(btn => {
        btn.onclick = () => {
            const p = btn.dataset.period;
            const now = new Date();
            const pad = n => String(n).padStart(2, '0');
            const toStr = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

            const today = toStr(now);
            $('to-date').value = today;

            if (p === 'all') {
                $('from-date').value = '';
                $('to-date').value = '';
            } else if (p === 'today') {
                $('from-date').value = today;
            } else if (p === 'week') {
                const past = new Date(now);
                past.setDate(past.getDate() - 7);
                $('from-date').value = toStr(past);
            } else if (p === 'half') {
                const day = now.getDate();
                const past = new Date(now);
                if (day > 15) {
                    past.setDate(16);
                } else {
                    past.setDate(1);
                }
                $('from-date').value = toStr(past);
            } else if (p === 'month') {
                const past = new Date(now.getFullYear(), now.getMonth(), 1);
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
                        loadEntries(),
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

    // -------------------------------------------------------------------------
    // INICIALIZACIÓN ULTRA RÁPIDA EN PARALELO
    // -------------------------------------------------------------------------
    Promise.all([
        loadRates(),
        loadProducts(),
        loadEntries(),
        loadLots(),
        loadInventoryMetrics()
    ]).catch(err => console.error('Error inicializando:', err));

})();

