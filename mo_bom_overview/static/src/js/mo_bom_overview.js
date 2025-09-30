/** @odoo-module **/

import { Component, onWillStart, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

export class MoBomOverview extends Component {
    static components = { Layout };
    static props = { ...standardActionServiceProps };
    static template = "mo_bom_overview.MoBomOverview";

    setup() {
        this.ormService = useService("orm");
        this.actionService = useService("action");

        this.state = useState({
            data: {},
            showAvailabilities: true,
            showCosts: true,
            showOperations: true,
            showLeadTimes: true,
            operationsCollapsed: false,
            byproductsCollapsed: false,
            indirectCostsCollapsed: false,
        });

        // Variables para almacenar el interval de refresco y observers
        this.refreshInterval = null;
        this.lastProductQty = null;
        this.lastState = null;
        this.domObserver = null;
        this.consecutiveErrors = 0;  //FIX: contador de errores consecutivos

        onWillStart(async () => {
            await this.loadData();
        });

        onMounted(() => {
            setTimeout(() => {
                this.startIntelligentPolling();
            }, 1000);
        });

        onWillUnmount(() => {
            this.stopDOMObserver();
            this.stopRefreshPolling();
        });
    }

    async loadData() {
        const activeId = this.props.action.context.active_id;

        try {
            //FIX 11: Usar método confiable para obtener datos de producción
            const productionInfo = await this.getReliableProductionData(activeId);

            // Usar la cantidad confiable
            const currentQty = productionInfo.product_qty;
            console.log(`🔍 Reliable product_qty from production: ${currentQty}`);

            //FIX 12: Obtener datos del reporte con cantidad confiable
            // MRP MODE: Activo por defecto (true) para precisión en valoración
            // Usa las mismas capas de valoración que mrp_workorder PERO incluye costos indirectos
            const mrpCompatibility = this.props.action.context.mrp_workorder_compatibility ?? true;
            console.log(`MRP Workorder compatibility mode: ${mrpCompatibility}`);

            const reportData = await this.ormService.call(
                "report.mo.bom.overview",
                "get_report_data",
                [activeId, currentQty, false, mrpCompatibility]
            );

            console.log(` Called get_report_data with reliable quantity: ${currentQty}`);

            // Configurar información del estado
            reportData.is_production_done = productionInfo.state === 'done';
            reportData.production_state = productionInfo.state;
            reportData.current_product_qty = productionInfo.product_qty;

            // Actualizar valores de referencia para el polling
            this.lastProductQty = productionInfo.product_qty;
            this.lastState = productionInfo.state;

            // Verificar y configurar información de moneda (mantenido igual)
            if (reportData.company_currency) {
                reportData.currency = reportData.company_currency;
                console.log('Currency loaded from backend:', reportData.currency);
            } else {
                console.warn('No currency info from backend, using fallback');
                reportData.currency = {
                    name: 'USD',
                    symbol: '$',
                    position: 'before'
                };
                reportData.company_currency = reportData.currency;
            }

            this.state.data = reportData;

            // Cambiar título de la ventana
            if (reportData.production_name) {
                const statusSuffix = reportData.is_production_done ? '' : ' (Estimado)';
                document.title = `Overview - ${reportData.production_name}${statusSuffix}`;
            }

            //FIX 13: Reset contador de errores si la carga fue exitosa
            this.consecutiveErrors = 0;

        } catch (error) {
            console.error("Error loading MO BOM Overview data:", error);
            this.consecutiveErrors++;

            // Si hay muchos errores consecutivos, parar el polling
            if (this.consecutiveErrors >= 5) {
                console.error("Too many consecutive errors, stopping polling");
                this.stopRefreshPolling();
            }

            // Datos de emergencia (mantenidos igual)
            this.state.data = {
                lines: {
                    name: 'Error al cargar datos',
                    quantity: 0,
                    uom_name: 'Unidades',
                    unit_cost: 0,
                    prod_cost: 0,
                    bom_cost: 0,
                    cost_variance: 0,
                    cost_variance_percentage: 0,
                    is_over_budget: false,
                    currency_id: false,
                    components: [],
                    operations: [],
                    byproducts: [],
                    indirect_costs: [],
                },
                production_name: 'Error',
                is_production_done: false,
                production_state: 'draft',
                currency: {
                    name: 'USD',
                    symbol: '$',
                    position: 'before'
                },
                company_currency: {
                    name: 'USD',
                    symbol: '$',
                    position: 'before'
                }
            };
        }
    }

    //FIX 14: Método para obtener datos de producción de forma confiable
    async getReliableProductionData(productionId) {
        try {
            const productionData = await this.ormService.call(
                "mrp.production",
                "refresh_production_data_for_client",
                [productionId]
            );

            if (productionData.success) {
                return productionData.data;
            } else {
                console.error("Error in reliable production data:", productionData.error);
                // Fallback a método estándar
                return await this.getStandardProductionData(productionId);
            }
        } catch (error) {
            console.warn("Reliable method failed, falling back to standard:", error);
            // Fallback a método estándar
            return await this.getStandardProductionData(productionId);
        }
    }

    async getStandardProductionData(productionId) {
        const productionInfo = await this.ormService.call(
            "mrp.production",
            "read",
            [productionId],
            {
                fields: ['state', 'name', 'product_qty']
            }
        );

        return productionInfo && productionInfo.length > 0 ? productionInfo[0] : {
            state: 'draft',
            name: 'Unknown',
            product_qty: 0
        };
    }

    getProductionStateText() {
        if (this.state.data.is_production_done) {
            return 'Costos Reales Aplicados';
        }

        const stateMap = {
            'draft': 'Borrador - Costos Estimados',
            'confirmed': 'Confirmado - Costos Estimados',
            'progress': 'En Progreso - Costos Estimados',
            'to_close': 'Por Cerrar - Costos Estimados',
            'cancel': 'Cancelado'
        };

        return stateMap[this.state.data.production_state] || 'Costos Estimados';
    }

    async onPrint() {
        const activeId = this.props.action.context.active_id;
        return this.actionService.doAction({
            type: "ir.actions.report",
            report_type: "qweb-pdf",
            report_name: "mo_bom_overview.report_mo_bom_overview_document",
            context: {
                'active_ids': [activeId],
                'active_model': 'mrp.production'
            }
        });
    }

    onToggleDisplay(option) {
        this.state[option] = !this.state[option];
    }

    formatMonetary(value, currencyId) {
        try {
            const numValue = parseFloat(value);
            if (isNaN(numValue)) {
                return "0.00";
            }

            const currency = this.state.data?.currency || { symbol: '$', position: 'before' };
            const formattedValue = numValue.toFixed(2);

            const numberWithCommas = formattedValue.replace(/\B(?=(\d{3})+(?!\d))/g, ",");

            if (currency.position === 'after') {
                return `${numberWithCommas} ${currency.symbol}`;
            } else {
                return `${currency.symbol}${numberWithCommas}`;
            }
        } catch (error) {
            console.warn("Error formatting monetary value:", error);
            return `$${parseFloat(value || 0).toFixed(2)}`;
        }
    }

    getCurrency(currencyId) {
        return { symbol: '$' };
    }

    hasAttachments(line) {
        return line.has_attachments || false;
    }

    getColorClass(state) {
        switch(state) {
            case 'available': return 'text-success';
            case 'expected': return 'text-warning';
            case 'unavailable': return 'text-danger';
            default: return '';
        }
    }

    // ===== MÉTODOS DE CÁLCULO DE COSTOS (mantenidos igual) =====

    getUnitCost() {
        if (this.state.data.lines?.unit_cost !== undefined) {
            return this.formatMonetary(this.state.data.lines.unit_cost, this.state.data.lines.currency_id);
        }

        const totalCost = this.getTotalCostWithLandedCosts();
        const quantity = this.state.data.lines?.quantity || 1;
        return this.formatMonetary(totalCost / quantity, this.state.data.lines.currency_id);
    }

    getTotalCostWithLandedCosts() {
        const componentsCost = this.getTotalComponentsCostValue();
        const operationsCost = this.getTotalOperationsCostValue();
        const indirectCost = this.getTotalIndirectCostsValue();
        return componentsCost + operationsCost + indirectCost;
    }

    getTotalComponentsCostValue() {
        if (!this.state.data.lines?.components) return 0;
        return this.state.data.lines.components.reduce((sum, comp) => {
            return sum + (comp.prod_cost || 0);
        }, 0);
    }

    getTotalComponentsCost() {
        return this.formatMonetary(this.getTotalComponentsCostValue(), this.state.data.lines.currency_id);
    }

    getComponentsCostPerUnit() {
        const total = this.getTotalComponentsCostValue();
        const quantity = this.state.data.lines?.quantity || 1;
        return this.formatMonetary(total / quantity, this.state.data.lines.currency_id);
    }

    getTotalOperationsCostValue() {
        if (!this.state.data.lines?.operations) return 0;
        return this.state.data.lines.operations.reduce((sum, op) => sum + (op.bom_cost || 0), 0);
    }

    getTotalOperationsCost() {
        return this.formatMonetary(this.getTotalOperationsCostValue(), this.state.data.lines.currency_id);
    }

    getTotalOperationsCostFormatted() {
        return this.formatMonetary(this.getTotalOperationsCostValue(), this.state.data.lines.currency_id);
    }

    getOperationsCostPerUnit() {
        const total = this.getTotalOperationsCostValue();
        const quantity = this.state.data.lines?.quantity || 1;
        return this.formatMonetary(total / quantity, this.state.data.lines.currency_id);
    }

    getTotalIndirectCostsValue() {
        if (!this.state.data.lines?.indirect_costs) return 0;
        return this.state.data.lines.indirect_costs.reduce((sum, cost) => sum + (cost.amount || 0), 0);
    }

    getTotalIndirectCosts() {
        return this.formatMonetary(this.getTotalIndirectCostsValue(), this.state.data.lines.currency_id);
    }

    getTotalRealCost() {
        if (this.state.data.lines?.prod_cost !== undefined) {
            return this.formatMonetary(this.state.data.lines.prod_cost, this.state.data.lines.currency_id);
        }

        return this.formatMonetary(this.getTotalCostWithLandedCosts(), this.state.data.lines.currency_id);
    }

    getCostBreakdown() {
        const componentsCost = this.getTotalComponentsCostValue();
        const operationsCost = this.getTotalOperationsCostValue();
        const indirectCost = this.getTotalIndirectCostsValue();
        const total = componentsCost + operationsCost + indirectCost;

        return {
            components: {
                value: componentsCost,
                formatted: this.formatMonetary(componentsCost, this.state.data.lines.currency_id),
                percentage: total > 0 ? ((componentsCost / total) * 100).toFixed(1) : 0
            },
            operations: {
                value: operationsCost,
                formatted: this.formatMonetary(operationsCost, this.state.data.lines.currency_id),
                percentage: total > 0 ? ((operationsCost / total) * 100).toFixed(1) : 0
            },
            indirect: {
                value: indirectCost,
                formatted: this.formatMonetary(indirectCost, this.state.data.lines.currency_id),
                percentage: total > 0 ? ((indirectCost / total) * 100).toFixed(1) : 0
            },
            total: {
                value: total,
                formatted: this.formatMonetary(total, this.state.data.lines.currency_id)
            }
        };
    }

    getCostComparison() {
        const realCost = this.state.data.lines?.prod_cost || 0;
        const bomCost = this.state.data.lines?.bom_cost || 0;
        const variance = realCost - bomCost;
        const variancePercentage = bomCost > 0 ? ((variance / bomCost) * 100).toFixed(1) : 0;

        return {
            planned: this.formatMonetary(bomCost, this.state.data.lines.currency_id),
            real: this.formatMonetary(realCost, this.state.data.lines.currency_id),
            variance: this.formatMonetary(Math.abs(variance), this.state.data.lines.currency_id),
            variancePercentage: variancePercentage,
            isOverBudget: variance > 0,
            isUnderBudget: variance < 0
        };
    }

    getLandedCostsSummary() {
        if (!this.state.data.lines?.indirect_costs || this.state.data.lines.indirect_costs.length === 0) {
            return null;
        }

        const totalIndirect = this.getTotalIndirectCostsValue();
        const quantity = this.state.data.lines?.quantity || 1;
        const unitIndirectCost = totalIndirect / quantity;

        return {
            total: this.formatMonetary(totalIndirect, this.state.data.lines.currency_id),
            perUnit: this.formatMonetary(unitIndirectCost, this.state.data.lines.currency_id),
            count: this.state.data.lines.indirect_costs.length,
            details: this.state.data.lines.indirect_costs.map(cost => ({
                name: cost.name,
                amount: this.formatMonetary(cost.amount, cost.currency_id),
                date: cost.date
            }))
        };
    }

    // ===== MÉTODOS DE CONTROL DE UI =====

    toggleOperations() {
        this.state.operationsCollapsed = !this.state.operationsCollapsed;
    }

    toggleByproducts() {
        this.state.byproductsCollapsed = !this.state.byproductsCollapsed;
    }

    toggleIndirectCosts() {
        this.state.indirectCostsCollapsed = !this.state.indirectCostsCollapsed;
    }

    getTotalByproductsCost() {
        if (!this.state.data.lines?.byproducts) return "0.00";
        const total = this.state.data.lines.byproducts.reduce((sum, bp) => sum + (bp.bom_cost || 0), 0);
        return this.formatMonetary(total, this.state.data.lines.currency_id);
    }

    getTotalOperationsHours() {
        if (!this.state.data.lines?.operations) return 0;
        return this.state.data.lines.operations.reduce((sum, op) => {
            const hours = (op.quantity || 0) / 60.0;
            return sum + hours;
        }, 0);
    }

    getCurrencySymbol() {
        try {
            return this.state.data?.currency?.symbol || '$';
        } catch (error) {
            console.warn("Error getting currency symbol:", error);
            return '$';
        }
    }

    getCurrencyName() {
        try {
            return this.state.data?.currency?.name || 'USD';
        } catch (error) {
            console.warn("Error getting currency name:", error);
            return 'USD';
        }
    }

    getCurrencyDisplayInfo() {
        try {
            const currency = this.state.data?.currency || {
                name: 'USD',
                symbol: '$',
                position: 'before'
            };

            return {
                symbol: currency.symbol || '$',
                name: currency.name || 'USD',
                position: currency.position || 'before',
                displayText: `${currency.name || 'USD'} (${currency.symbol || '$'})`
            };
        } catch (error) {
            console.warn("Error getting currency display info:", error);
            return {
                symbol: '$',
                name: 'USD',
                position: 'before',
                displayText: 'USD ($)'
            };
        }
    }

    hasCurrencyInfo() {
        return !!(this.state.data?.currency?.symbol);
    }

    // ===== MÉTODOS DE REFRESCO AUTOMÁTICO MEJORADOS =====

    stopDOMObserver() {
        if (this.domObserver) {
            this.domObserver.disconnect();
            this.domObserver = null;
            console.log('Stopped DOM observer');
        }
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
            this.refreshInterval = null;
            console.log('Stopped refresh polling');
        }
    }

    stopRefreshPolling() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
            this.refreshInterval = null;
            console.log('Stopped refresh polling');
        }
    }

    //FIX 15: Polling inteligente mejorado con mejor manejo de errores
    startIntelligentPolling() {
        console.log('startIntelligentPolling called - Current state:', this.state.data.production_state);
        console.log('Current product_qty:', this.lastProductQty);

        // Solo observar cambios en estados relevantes
        if (this.state.data.production_state === 'confirmed' ||
            this.state.data.production_state === 'progress') {

            let pollInterval = 1000; // Empezar con 1 segundo
            let inactivityCount = 0;
            let errorCount = 0;

            const executePoll = async () => {
                try {
                    const changed = await this.checkForProductQtyChanges();

                    if (changed) {
                        pollInterval = 1000;
                        inactivityCount = 0;
                        errorCount = 0; // Reset errores si hay cambios
                        console.log('Change detected, keeping fast polling');
                    } else {
                        inactivityCount++;
                        // Incrementar gradualmente el intervalo si no hay actividad
                        if (inactivityCount > 5 && pollInterval < 3000) {
                            pollInterval = 3000;
                            console.log('📉 No recent changes, slowing down polling to 3s');
                        } else if (inactivityCount > 10 && pollInterval < 5000) {
                            pollInterval = 5000;
                            console.log('📉 Extended inactivity, slowing down polling to 5s');
                        }
                    }
                } catch (error) {
                    errorCount++;
                    console.error(`Polling error (${errorCount}/5):`, error);

                    // Si hay muchos errores, detener polling
                    if (errorCount >= 5) {
                        console.error('Too many polling errors, stopping');
                        this.stopRefreshPolling();
                        return;
                    }

                    // Incrementar intervalo si hay errores
                    pollInterval = Math.min(pollInterval * 1.5, 10000);
                }
            };

            this.refreshInterval = setInterval(executePoll, pollInterval);
            console.log(`⚡ Started intelligent polling with ${pollInterval}ms interval`);
        } else {
            console.log('Polling not started - state is:', this.state.data.production_state);
        }
    }

    //FIX 16: Verificación mejorada de cambios con mejor logging
    async checkForProductQtyChanges() {
        try {
            const activeId = this.props.action.context.active_id;

            // Usar método confiable para verificar cambios
            const currentInfo = await this.getReliableProductionData(activeId);

            if (currentInfo) {
                const currentQty = currentInfo.product_qty;
                const currentState = currentInfo.state;

                // Verificar si cambió la cantidad o el estado
                const qtyChanged = this.lastProductQty !== currentQty;
                const stateChanged = this.lastState !== currentState;

                if (qtyChanged || stateChanged) {
                    console.log(`CHANGE DETECTED - Qty: ${this.lastProductQty} -> ${currentQty}, State: ${this.lastState} -> ${currentState}`);

                    // Actualizar valores de referencia
                    this.lastProductQty = currentQty;
                    this.lastState = currentState;

                    // Recargar todos los datos
                    await this.refreshData();

                    return true;
                }

                // Si el estado cambió a 'done', detener el polling
                if (currentState === 'done' && this.state.data.production_state !== 'done') {
                    console.log('State changed to done - stopping polling');
                    this.stopRefreshPolling();
                }
            }

            return false;
        } catch (error) {
            console.warn('Error checking for product_qty changes:', error);
            throw error; // Re-throw para que el polling maneje el error
        }
    }

    async refreshData() {
        try {
            await this.loadData();
            console.log(' Data refreshed successfully');
        } catch (error) {
            console.error(' Error refreshing data:', error);
            throw error;
        }
    }

    //FIX 17: Método público mejorado para refresco manual
    async manualRefresh() {
        try {
            console.log('Manual refresh triggered');
            await this.refreshData();

            // Mostrar feedback visual al usuario
            const refreshButton = document.querySelector('button[title="Actualizar datos manualmente"]');
            if (refreshButton) {
                const originalText = refreshButton.innerHTML;
                refreshButton.innerHTML = '<i class="fa fa-check"/> ¡Actualizado!';
                refreshButton.disabled = true;

                setTimeout(() => {
                    refreshButton.innerHTML = originalText;
                    refreshButton.disabled = false;
                }, 2000);
            }

        } catch (error) {
            console.error(' Manual refresh failed:', error);

            // Mostrar error al usuario
            const refreshButton = document.querySelector('button[title="Actualizar datos manualmente"]');
            if (refreshButton) {
                const originalText = refreshButton.innerHTML;
                refreshButton.innerHTML = '<i class="fa fa-exclamation-triangle"/> Error';
                refreshButton.classList.add('btn-danger');

                setTimeout(() => {
                    refreshButton.innerHTML = originalText;
                    refreshButton.classList.remove('btn-danger');
                }, 3000);
            }
        }
    }
}

registry.category("actions").add("mo_bom_overview", MoBomOverview);