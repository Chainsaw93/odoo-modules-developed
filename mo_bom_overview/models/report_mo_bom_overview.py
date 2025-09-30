from odoo import api, fields, models, _
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)

class ReportMoBomOverview(models.AbstractModel):
    _name = 'report.mo.bom.overview'
    _description = 'MO BOM Overview Report - MO data with BOM format'

    @api.model
    def _get_report_values(self, docids, data=None):
        """Método requerido para reportes QWeb"""
        if not docids:
            return {}

        production_id = self.env.context.get('active_id') or docids[0]
        quantity_to_use = self.env.context.get('production_qty_to_use')

        report_data = self.get_report_data(production_id, quantity_to_use, False)

        return {
            'docs': [report_data],
            'doc_ids': docids,
            'doc_model': 'mrp.production',
        }

    @api.model
    def get_report_data(self, production_id, quantity_to_use=False, searchVariant=False, mrp_workorder_compatibility=True):
        """Obtiene datos del MO Overview con precisión mejorada y costos indirectos

        Args:
            production_id: ID de la orden de fabricación
            quantity_to_use: Cantidad a usar (opcional, usa la de la orden si no se especifica)
            searchVariant: No usado actualmente
            mrp_workorder_compatibility: Por defecto True para precisión en valoración
                - True: Usa capas de valoración históricas precisas (como mrp_workorder)
                - False: Usa precios standard_price simples

        IMPORTANTE: A diferencia de Vista General, SIEMPRE incluye costos indirectos (landed costs)
        """

        #  FIX 1: Lectura confiable con invalidación específica
        production = self._get_reliable_production_data(production_id)

        if not production.exists():
            return {}

        _logger.info(f"=== get_report_data for MO {production.name} ===")
        _logger.info(f"Production state: {production.state}")
        _logger.info(f"📊 mo_bom_overview incluye: Valoración precisa + Costos indirectos")

        # Crear nuevo contexto con el modo de compatibilidad y estado de producción
        new_context = dict(self.env.context)
        new_context['_mrp_workorder_mode'] = mrp_workorder_compatibility
        new_context['production_state'] = production.state
        self = self.with_context(new_context)

        #  FIX 2: Lectura confiable de product_qty
        current_product_qty = self._get_reliable_product_qty(production)
        _logger.info(f"Reliable product_qty from BD: {current_product_qty}")
        _logger.info(f"Received quantity_to_use parameter: {quantity_to_use} (type: {type(quantity_to_use)})")

        # === Mejorada lógica de selección de cantidad ===
        production_qty_to_use = current_product_qty  # Default: usar valor confiable de BD

        if quantity_to_use is not False and quantity_to_use is not None:
            try:
                converted_qty = float(quantity_to_use)
                if converted_qty > 0:
                    production_qty_to_use = converted_qty
                    _logger.info(f" Using quantity from parameter: {production_qty_to_use}")
                else:
                    _logger.warning(f" Quantity from parameter is <= 0: {converted_qty}, using reliable BD value: {current_product_qty}")
            except (ValueError, TypeError) as e:
                _logger.warning(f" Invalid quantity from parameter '{quantity_to_use}': {e}, using reliable BD value: {current_product_qty}")
        else:
            _logger.info(f" No quantity parameter provided, using reliable BD value: {current_product_qty}")

        _logger.info(f" Final product_qty to use: {production_qty_to_use}")

        #  CONTEXTO TEMPORAL: Determinar fecha de referencia para precios históricos
        reference_date = self._get_reference_date(production)
        _logger.info(f"📅 MO {production.name} - Reference date for pricing: {reference_date}")
        _logger.info(f"📊 MO {production.name} - Quantity: {production_qty_to_use}, State: {production.state}")

        # LÓGICA UNIFICADA: Usar siempre cálculos estimados para componentes y operaciones
        is_production_done = production.state == 'done'

        _logger.info("Using UNIFIED calculation logic for components and operations")
        bom_format_data = self._calculate_estimated_data(production, production_qty_to_use, reference_date)

        # SIEMPRE incluir landed costs - esta es la funcionalidad diferenciadora de mo_bom_overview
        if is_production_done:
            _logger.info("Using REAL landed costs (state='done' only)")
            real_landed_costs = self._get_landed_costs_real_only(production)
            bom_format_data['indirect_costs'] = real_landed_costs
            total_landed_costs = sum(lc.get('amount', 0) for lc in real_landed_costs)
        else:
            _logger.info("Using ESTIMATED landed costs (all states)")
            estimated_landed_costs = self._get_landed_costs_estimated(production)
            bom_format_data['indirect_costs'] = estimated_landed_costs
            total_landed_costs = sum(lc.get('amount', 0) for lc in estimated_landed_costs)

        # Recalcular totales finales con landed costs apropiados
        components_cost = sum(comp.get('prod_cost', 0) for comp in bom_format_data.get('components', []))
        operations_cost = sum(op.get('bom_cost', 0) for op in bom_format_data.get('operations', []))

        total_cost = components_cost + operations_cost + total_landed_costs
        unit_cost = total_cost / production_qty_to_use if production_qty_to_use and production_qty_to_use > 0 else 0

        # Actualizar línea principal con valores finales
        bom_format_data.update({
            'prod_cost': total_cost,
            'unit_cost': unit_cost,
        })

        _logger.info(f"📊 RESUMEN FINAL mo_bom_overview para {production.name}:")
        _logger.info(f"  Componentes: {components_cost:.2f}")
        _logger.info(f"  Operaciones: {operations_cost:.2f}")
        _logger.info(f"  Subtotal (como Vista General): {components_cost + operations_cost:.2f}")
        _logger.info(f"  + Costos Indirectos: {total_landed_costs:.2f}")
        _logger.info(f"  = TOTAL mo_bom_overview: {total_cost:.2f}")
        _logger.info(f"  Diferencia vs Vista General: +{total_landed_costs:.2f} (costos indirectos)")

        currency_info = self._get_safe_currency_info(production)

        return {
            'lines': bom_format_data,
            'production_name': production.name,
            'production_id': production.id,
            'production_state': production.state,
            'is_production_done': is_production_done,
            'is_uom_applied': self.env.user.has_group('uom.group_uom'),
            'state_display': dict(production._fields['state'].selection).get(production.state, production.state),
            **currency_info
        }

    #  FIX 3: Nuevos métodos para lectura confiable
    def _get_reliable_production_data(self, production_id):
        """Obtiene datos confiables de producción con invalidación específica"""
        production = self.env['mrp.production'].browse(production_id)

        if not production.exists():
            return production

        # Invalidar campos críticos específicos
        critical_fields = ['product_qty', 'state', 'name', 'product_id', 'product_uom_id']
        production.invalidate_recordset(critical_fields)

        # También invalidar move_raw_ids que pueden haber cambiado
        production.move_raw_ids.invalidate_recordset(['product_uom_qty'])

        _logger.debug(f"Cache invalidated for MO {production_id}, fields: {critical_fields}")

        return production

    def _get_reliable_product_qty(self, production):
        """Lectura confiable de product_qty actualizada"""
        try:
            # Forzar flush de la BD
            production.flush_recordset(['product_qty'])

            # Consulta SQL directa para máxima confiabilidad
            self.env.cr.execute("""
                SELECT product_qty
                FROM mrp_production
                WHERE id = %s
            """, (production.id,))
            result = self.env.cr.fetchone()

            if result:
                qty = result[0]
                _logger.info(f"✅ Reliable qty from DB for MO {production.name}: {qty}")
                return qty

            _logger.warning(f"⚠️ No qty found in DB for MO {production.name}, using fallback")
            return production.product_qty

        except Exception as e:
            _logger.error(f"Error getting reliable qty: {e}")
            return production.product_qty

    #  FIX 4: Método de debugging para diagnosticar problemas futuros
    def _debug_cache_consistency(self, production):
        """Método para diagnosticar problemas de caché"""
        try:
            # Leer valor actual (posiblemente cacheado)
            cached_value = production.product_qty

            # Invalidar y releer
            production.invalidate_recordset(['product_qty'])
            fresh_value = production.product_qty

            # Leer directamente de BD
            self.env.cr.execute(
                "SELECT product_qty FROM mrp_production WHERE id = %s",
                (production.id,)
            )
            db_result = self.env.cr.fetchone()
            db_value = db_result[0] if db_result else None

            # Comparar valores
            consistency_info = {
                'mo_name': production.name,
                'cached': cached_value,
                'fresh': fresh_value,
                'database': db_value,
                'is_consistent': cached_value == fresh_value == db_value
            }

            # Debug/warning logs removed for production

            return consistency_info

        except Exception as e:
            _logger.error(f"Error in cache consistency check: {e}")
            return {'error': str(e)}

    def _calculate_estimated_data(self, production, production_qty_override=None, reference_date=None):
        """Calcula datos estimados CONSISTENTES para cualquier estado de orden"""
        # Preferir la cantidad pasada por el llamador (lectura confiable previa).
        # Si no se pasa override, intentar obtener una lectura fiable desde la BD;
        # como último recurso usar el valor cacheado `production.product_qty`.
        if production_qty_override is not None and production_qty_override is not False:
            production_qty_to_use = production_qty_override
        else:
            try:
                production_qty_to_use = self._get_reliable_product_qty(production)
            except Exception:
                production_qty_to_use = production.product_qty

        _logger.info(f"=== DEBUG _calculate_estimated_data for {production.name} (ref_date: {reference_date}) ===")

        # Calcular costos estimados usando SIEMPRE la misma lógica CON fecha de referencia
        estimated_components_cost = self._calculate_consistent_components_cost(production, reference_date)
        estimated_operations_cost = self._calculate_consistent_operations_cost(production)

        # En modo mrp_workorder, hacer resumen detallado
        if self.env.context.get('_mrp_workorder_mode'):
            _logger.info(f"💰 MRP_MODE SUMMARY for {production.name}:")
            _logger.info(f"   Components cost: {estimated_components_cost:.2f}")
            _logger.info(f"   Operations cost: {estimated_operations_cost:.2f}")
            _logger.info(f"   TOTAL (without landed): {estimated_components_cost + estimated_operations_cost:.2f}")
        else:
            _logger.info(f"Consistent calculation - Components: {estimated_components_cost}, Operations: {estimated_operations_cost}")

        # Costo base (sin landed costs)
        base_cost = estimated_components_cost + estimated_operations_cost
        unit_cost_base = base_cost / production_qty_to_use if production_qty_to_use else 0

        # Costo BOM para comparación
        bom_cost = self._calculate_consistent_bom_cost(production, reference_date)

        _logger.info(f"Base cost: {base_cost}, Unit cost: {unit_cost_base}, BOM cost: {bom_cost}")

        # Línea principal usando datos consistentes
        main_line = {
            'name': production.product_id.display_name,
            'quantity': production.qty_producing if production.state != 'done' else production.qty_produced,
            'uom_name': production.product_uom_id.name,
            'unit_cost': unit_cost_base,
            'prod_cost': base_cost,
            'bom_cost': bom_cost,
            'cost_variance': base_cost - bom_cost,
            'cost_variance_percentage': self._calculate_variance_percentage_from_values(base_cost, bom_cost),
            'is_over_budget': base_cost > bom_cost,
            'currency': production.company_id.currency_id,
            'currency_id': production.company_id.currency_id.id,
            'code': production.bom_id.code if production.bom_id else '',

            # Secciones consistentes
            'components': self._get_consistent_components(production, reference_date),
            'operations': self._get_consistent_operations(production),
            'byproducts': self._get_consistent_byproducts(production, reference_date),
            'indirect_costs': [],
        }

        return main_line

    def _calculate_consistent_components_cost(self, production, reference_date=None):
        """Cálculo CONSISTENTE de costos de componentes usando cantidades reales modificadas"""
        total_cost = 0

        #  FIX 5: Asegurar datos frescos de move_raw_ids - incluir should_consume_qty
        fields_to_invalidate = ['product_uom_qty']
        if 'should_consume_qty' in production.move_raw_ids._fields:
            fields_to_invalidate.append('should_consume_qty')
        production.move_raw_ids.invalidate_recordset(fields_to_invalidate)

        for move_line in production.move_raw_ids:
            # Usar should_consume_qty si está disponible (como Vista General)
            if hasattr(move_line, 'should_consume_qty') and move_line.should_consume_qty:
                qty_needed = move_line.should_consume_qty
            else:
                qty_needed = move_line.product_uom_qty

            #  PRECIO INTELIGENTE: Usar jerarquía de fuentes más confiable CON fecha de referencia
            mrp_mode = self.env.context.get('_mrp_workorder_mode', False)
            component_cost = self._get_reliable_product_cost(
                move_line.product_id,
                move_line,
                date=reference_date,
                mrp_workorder_mode=mrp_mode
            )

            # Logging detallado para debugging
            component_total = qty_needed * component_cost

            # En modo mrp_workorder, hacer logging más detallado para detectar diferencias
            if mrp_mode:
                _logger.info(f" MRP_MODE Component: {move_line.product_id.default_code or move_line.product_id.name}")
                _logger.info(f"   Qty: {qty_needed:.6f} × Unit Cost: {component_cost:.6f} = Total: {component_total:.6f}")
            else:
                _logger.debug(f" Component: {move_line.product_id.name} - Qty: {qty_needed}, Unit Cost: {component_cost}, Total: {component_total}")

            # Costo total del componente con cantidad real
            total_cost += component_total

        return total_cost

    def _calculate_consistent_operations_cost(self, production):
        """Cálculo CONSISTENTE de costos de operaciones"""
        total_cost = 0

        #  FIX 6: Asegurar datos frescos de workorder_ids
        production.workorder_ids.invalidate_recordset(['duration_expected'])

        for workorder in production.workorder_ids:
            # Duración esperada del workorder
            duration_expected = getattr(workorder, 'duration_expected', 0) or 0

            # Convertir minutos a horas
            duration_hours = duration_expected / 60.0 if duration_expected > 0 else 0

            # CONSISTENCIA: Usar costo por hora consistente
            hourly_cost = self._get_consistent_hourly_cost(workorder)

            # Costo de esta operación
            operation_cost = duration_hours * hourly_cost
            total_cost += operation_cost

        return total_cost

    def _get_consistent_hourly_cost(self, workorder):
        """Obtiene costo por hora CONSISTENTE - prioriza empleado asignado, fallback a workcenter"""
        hourly_cost = 0

        # Estrategia consistente para obtener empleado responsable
        employee = None

        # Prioridad 1: employee_assigned_ids (más confiable)
        if hasattr(workorder, 'employee_assigned_ids') and workorder.employee_assigned_ids:
            employee = workorder.employee_assigned_ids[0]
        # Prioridad 2: employee_id (singular)
        elif hasattr(workorder, 'employee_id') and workorder.employee_id:
            employee = workorder.employee_id
        # Prioridad 3: employee_ids (plural)
        elif hasattr(workorder, 'employee_ids') and workorder.employee_ids:
            employee = workorder.employee_ids[0]

        # Obtener costo del empleado
        if employee:
            hourly_cost = getattr(employee, 'hourly_cost', 0) or 0

        # Fallback: costo del centro de trabajo
        if not hourly_cost and workorder.workcenter_id:
            hourly_cost = getattr(workorder.workcenter_id, 'costs_hour', 0) or 0

        return hourly_cost

    def _get_consistent_components(self, production, reference_date=None):
        """Lista CONSISTENTE de componentes usando la misma prioridad de campos que la Vista General de MRP"""
        components = []
        try:
            # Re-browse para forzar lectura fresca del registro principal
            production = self.env['mrp.production'].browse(production.id)

            # Re-browse de los moves para evitar valores cacheados
            moves = self.env['stock.move'].browse(production.move_raw_ids.ids)

            # Campos que necesitamos leer; filtrar por los que realmente existen en el modelo
            # Prioridad: 'quantity' (usado por Vista General), luego 'product_uom_qty', luego 'should_consume_qty' si aplica
            desired_fields = ['quantity', 'product_uom_qty', 'should_consume_qty', 'product_uom', 'product_id']
            available_fields = set(moves._fields.keys()) if moves else set()
            read_fields = [f for f in desired_fields if f in available_fields]

            # Siempre leer el id para mapear después
            if read_fields:
                read_fields = list(dict.fromkeys(['id'] + read_fields))  # id first, sin duplicados
                moves_data = {r['id']: r for r in moves.read(read_fields)}
            else:
                moves_data = {}

            # No forzamos factor salvo que BOM indique distinto; seguir comportamiento de Vista General
            bom_qty = production.bom_id.product_qty if production.bom_id else production.product_qty or 1.0
            mo_qty = production.product_qty or 0.0
            factor = (mo_qty / bom_qty) if bom_qty else 1.0

            for move in moves:
                try:
                    md = moves_data.get(move.id, {})

                    # Prioridad idéntica a MRP overview: usar 'quantity' si existe (campo mostrado por la vista),
                    # fallback a 'product_uom_qty', finalmente usar 'should_consume_qty' sólo si necesario.
                    if 'quantity' in md and md.get('quantity') is not None:
                        qty_to_consume = md.get('quantity')
                    elif 'product_uom_qty' in md and md.get('product_uom_qty') is not None:
                        qty_to_consume = md.get('product_uom_qty')
                    elif 'should_consume_qty' in md and md.get('should_consume_qty') is not None:
                        qty_to_consume = md.get('should_consume_qty')
                    else:
                        # Último recurso: usar atributos ORM (fuerza fetch si hace falta)
                        qty_to_consume = getattr(move, 'quantity', None)
                        if qty_to_consume is None:
                            qty_to_consume = getattr(move, 'product_uom_qty', 0.0)

                    # Aplicar factor sólo si la BOM está definida y la Vista General lo aplica: mantener proporciones
                    qty_to_consume = (qty_to_consume or 0.0) * factor

                    # Obtener costo usando la lógica existente (sin SQL)
                    unit_cost = self._get_reliable_product_cost(
                        move.product_id,
                        move,
                        date=reference_date,
                        mrp_workorder_mode=self.env.context.get('_mrp_workorder_mode', False)
                    )

                    total_cost = qty_to_consume * (unit_cost or 0.0)

                    components.append({
                        'name': move.product_id.display_name,
                        'quantity': qty_to_consume,
                        'uom_name': (move.product_uom.name if hasattr(move, 'product_uom') and move.product_uom else (md.get('product_uom') and self.env['uom.uom'].browse(md.get('product_uom')).name) or ''),
                        'prod_cost': total_cost,
                        'bom_cost': total_cost,
                        'currency_id': production.company_id.currency_id.id if production.company_id and production.company_id.currency_id else False,
                        'has_landed_costs': False,
                    })
                except Exception as exc_move:
                    _logger.exception(f"Error processing component move {move.id}: {exc_move}")
                    continue

        except Exception as e:
            _logger.exception(f"Error in _get_consistent_components: {e}")

        return components

    def _get_consistent_operations(self, production):
        """Lista CONSISTENTE de operaciones"""
        operations = []

        #  FIX 8: Invalidar caché de workorders
        production.workorder_ids.invalidate_recordset(['name', 'duration_expected'])

        for workorder in production.workorder_ids:
            # Duración esperada
            duration_expected = getattr(workorder, 'duration_expected', 0) or 0
            duration_hours = duration_expected / 60.0 if duration_expected > 0 else 0

            # Costo consistente
            hourly_cost = self._get_consistent_hourly_cost(workorder)
            operation_cost = duration_hours * hourly_cost

            # Nombre con empleado si está asignado
            operation_name = workorder.name
            employee_name = self._get_workorder_employee_name(workorder)
            if employee_name:
                operation_name = f"{workorder.name}: {employee_name}"

            operations.append({
                'name': operation_name,
                'quantity': duration_expected,  # En minutos para el frontend
                'uom_name': 'Minutos',
                'bom_cost': operation_cost,
                'currency_id': production.company_id.currency_id.id,
            })

        return operations

    def _get_workorder_employee_name(self, workorder):
        """Obtiene nombre del empleado asignado de forma consistente"""
        if hasattr(workorder, 'employee_assigned_ids') and workorder.employee_assigned_ids:
            return workorder.employee_assigned_ids[0].name
        elif hasattr(workorder, 'employee_id') and workorder.employee_id:
            return workorder.employee_id.name
        elif hasattr(workorder, 'employee_ids') and workorder.employee_ids:
            return workorder.employee_ids[0].name
        return None

    def _get_consistent_byproducts(self, production, reference_date=None):
        """Lista CONSISTENTE de byproducts"""
        byproducts = []
        if not production.bom_id or not hasattr(production.bom_id, 'byproduct_ids'):
            return byproducts

        # Usar cantidad confiable
        current_qty = self._get_reliable_product_qty(production)

        for byproduct_line in production.bom_id.byproduct_ids:
            # Cantidad estimada
            qty_estimated = byproduct_line.product_qty * current_qty / production.bom_id.product_qty

            #  PRECIO INTELIGENTE: Usar jerarquía de fuentes más confiable CON fecha de referencia
            mrp_mode = self.env.context.get('_mrp_workorder_mode', False)
            unit_cost = self._get_reliable_product_cost(
                byproduct_line.product_id,
                date=reference_date,
                mrp_workorder_mode=mrp_mode
            )
            total_cost = qty_estimated * unit_cost

            byproducts.append({
                'name': byproduct_line.product_id.display_name,
                'quantity': qty_estimated,
                'uom_name': byproduct_line.product_uom_id.name,
                'prod_cost': total_cost,
                'bom_cost': total_cost,
                'currency_id': production.company_id.currency_id.id,
            })

        return byproducts

    def _calculate_consistent_bom_cost(self, production, reference_date=None):
        """Calcula el costo BOM de forma CONSISTENTE usando cantidades reales"""
        # Calcular costo de componentes usando cantidades reales de move_raw_ids
        components_cost = 0

        # Usar datos frescos - incluir should_consume_qty
        fields_to_invalidate = ['product_uom_qty']
        if 'should_consume_qty' in production.move_raw_ids._fields:
            fields_to_invalidate.append('should_consume_qty')
        production.move_raw_ids.invalidate_recordset(fields_to_invalidate)

        for move_line in production.move_raw_ids:
            # Usar should_consume_qty si está disponible (como Vista General)
            if hasattr(move_line, 'should_consume_qty') and move_line.should_consume_qty:
                qty_needed = move_line.should_consume_qty
            else:
                qty_needed = move_line.product_uom_qty
            #  PRECIO INTELIGENTE: Usar jerarquía de fuentes más confiable CON fecha de referencia
            mrp_mode = self.env.context.get('_mrp_workorder_mode', False)
            unit_cost = self._get_reliable_product_cost(
                move_line.product_id,
                move_line,
                date=reference_date,
                mrp_workorder_mode=mrp_mode
            )
            components_cost += qty_needed * unit_cost

        # Costo de operaciones (este no se modifica, sigue usando BOM)
        operations_cost = 0
        if production.bom_id and hasattr(production.bom_id, 'operation_ids'):
            current_qty = self._get_reliable_product_qty(production)
            for operation in production.bom_id.operation_ids:
                # Tiempo por la cantidad de producción
                time_needed = operation.time_cycle * current_qty / production.bom_id.product_qty
                # Costo del centro de trabajo
                workcenter_cost = getattr(operation.workcenter_id, 'costs_hour', 0) or 0
                operations_cost += (time_needed / 60.0) * workcenter_cost

        return components_cost + operations_cost

    def _calculate_variance_percentage_from_values(self, real_cost, bom_cost):
        """Calcula porcentaje de variación"""
        if bom_cost > 0:
            return ((real_cost - bom_cost) / bom_cost) * 100
        return 0

    def _get_landed_costs_real_only(self, production):
        """Obtiene SOLO landed costs realmente aplicados (state='done')"""
        landed_costs = self.env['stock.landed.cost'].search([
            ('mrp_production_ids', 'in', production.id),
            ('state', '=', 'done')
        ])

        costs = []
        for lc in landed_costs:
            for cost_line in lc.cost_lines:
                costs.append({
                    'name': f"{lc.name} - {cost_line.name} (Aplicado)",
                    'amount': cost_line.price_unit,
                    'currency_id': lc.currency_id.id,
                    'date': lc.date,
                })
        return costs

    def _get_landed_costs_estimated(self, production):
        """Obtiene landed costs estimados (todos los estados relevantes)"""
        landed_costs = self.env['stock.landed.cost'].search([
            ('mrp_production_ids', 'in', production.id),
            ('state', 'in', ['draft', 'confirmed', 'done'])
        ])

        costs = []
        for lc in landed_costs:
            for cost_line in lc.cost_lines:
                state_label = {
                    'draft': 'Borrador',
                    'confirmed': 'Confirmado',
                    'done': 'Aplicado'
                }.get(lc.state, lc.state)

                costs.append({
                    'name': f"{lc.name} - {cost_line.name} ({state_label})",
                    'amount': cost_line.price_unit,
                    'currency_id': lc.currency_id.id,
                    'date': lc.date,
                })
        return costs

    def _get_historical_valuation_cost(self, product, reference_date=None):
        """Obtiene el costo de valoración histórico más cercano a la fecha de referencia

        Args:
            product: Producto para buscar la valoración
            reference_date: Fecha de referencia (ej: date_start de la MO)

        Returns:
            float: Unit cost de la capa de valoración más apropiada
        """
        _logger.debug(f"🔍 HISTORICAL VALUATION for {product.name} at reference_date: {reference_date}")

        if not reference_date:
            # Sin fecha de referencia, usar la más reciente
            try:
                # Detectar el campo de fecha correcto
                date_field = 'create_date'
                if 'stock.valuation.layer' in self.env and self.env['stock.valuation.layer']._fields.get('date'):
                    date_field = 'date'

                valuation_layers = self.env['stock.valuation.layer'].search([
                    ('product_id', '=', product.id),
                    ('company_id', '=', self.env.company.id)
                ], limit=1, order=f'{date_field} desc')
                if valuation_layers:
                    _logger.info(f"📊 No reference date, using latest valuation: {valuation_layers.unit_cost} for {product.name}")
                    return valuation_layers.unit_cost
            except Exception as e:
                _logger.warning(f"Error getting latest valuation for {product.name}: {e}")
            return 0

        try:
            # Detectar el campo de fecha correcto
            date_field = 'create_date'
            if 'stock.valuation.layer' in self.env and self.env['stock.valuation.layer']._fields.get('date'):
                date_field = 'date'
                _logger.info(f"✅ Using 'date' field for stock.valuation.layer")
            else:
                _logger.info(f"📝 Using 'create_date' field for stock.valuation.layer")

            # Buscar capas de valoración
            all_layers = self.env['stock.valuation.layer'].search([
                ('product_id', '=', product.id),
                ('company_id', '=', self.env.company.id)
            ], order=f'{date_field} desc', limit=5)

            if all_layers:
                # En modo mrp_workorder, hacer logging más visible
                if self.env.context.get('_mrp_workorder_mode'):
                    _logger.info(f"📋 Found {len(all_layers)} valuation layers for {product.name}:")
                    for layer in all_layers:
                        layer_date = getattr(layer, date_field, None)
                        _logger.info(f"   - {date_field}: {layer_date}, Unit cost: {layer.unit_cost}, Quantity: {layer.quantity}")
                else:
                    _logger.debug(f"📋 Found {len(all_layers)} valuation layers for {product.name}:")
                    for layer in all_layers:
                        layer_date = getattr(layer, date_field, None)
                        _logger.debug(f"   - {date_field}: {layer_date}, Unit cost: {layer.unit_cost}, Quantity: {layer.quantity}")

            # Buscar capa de consumo propia para órdenes completadas (estado 'done')
            # Esto asegura que mostramos el costo histórico real de lo que se consumió
            # MRP mode está activo por defecto, así que siempre aplicamos esta lógica

            if self.env.context.get('production_state') == 'done':
                # Para órdenes COMPLETADAS: buscar la capa de consumo específica
                # Esta capa refleja el costo real al momento del consumo
                exact_layer = self.env['stock.valuation.layer'].search([
                    ('product_id', '=', product.id),
                    ('company_id', '=', self.env.company.id),
                    (date_field, '>=', reference_date),  # Capas en o después de la fecha
                    (date_field, '<=', reference_date + timedelta(hours=2)),  # Dentro de 2 horas (por seguridad)
                    ('quantity', '<', 0)  # Consumos (cantidades negativas)
                ], limit=1, order=f'{date_field} asc')

                if exact_layer:
                    cost = exact_layer.unit_cost
                    layer_date = getattr(exact_layer, date_field, None)
                    _logger.info(f"✅ Using EXACT consumption layer for {product.name}: {cost} at {layer_date} (ref: {reference_date})")
                    return cost

            # Si no hay capa exacta, buscar la capa de valoración más cercana ANTERIOR
            valuation_layers = self.env['stock.valuation.layer'].search([
                ('product_id', '=', product.id),
                ('company_id', '=', self.env.company.id),
                (date_field, '<', reference_date)  # Solo capas ANTERIORES a la fecha
            ], limit=1, order=f'{date_field} desc')  # La más reciente antes de la fecha

            if valuation_layers:
                cost = valuation_layers.unit_cost
                layer_date = getattr(valuation_layers, date_field, None)
                _logger.info(f"✅ Found historical valuation for {product.name}: {cost} at {layer_date} (ref: {reference_date})")
                return cost
            else:
                # Si no hay capas anteriores, buscar la primera capa disponible
                valuation_layers = self.env['stock.valuation.layer'].search([
                    ('product_id', '=', product.id),
                    ('company_id', '=', self.env.company.id)
                ], limit=1, order=f'{date_field} asc')  # La más antigua disponible

                if valuation_layers:
                    cost = valuation_layers.unit_cost
                    layer_date = getattr(valuation_layers, date_field, None)
                    _logger.info(f"⚠️ No prior valuation, using earliest available for {product.name}: {cost} at {layer_date} (ref: {reference_date})")
                    return cost
                else:
                    _logger.warning(f"❌ No valuation layers found for {product.name}")
                    return 0

        except Exception as e:
            _logger.error(f"Error getting historical valuation for {product.name} at {reference_date}: {e}")
            return 0

    def _get_reference_date(self, production):
        """Determina la fecha de referencia para búsqueda de precios históricos

        Prioridad:
        1. date_start (fecha real de inicio)
        2. date_planned_start (fecha planificada)
        3. create_date (fecha de creación)
        """
        reference_date = None

        # Prioridad 1: date_start (fecha real de inicio)
        if hasattr(production, 'date_start') and production.date_start:
            reference_date = production.date_start
            _logger.debug(f"Using date_start as reference: {reference_date}")

        # Prioridad 2: date_planned_start (fecha planificada)
        elif hasattr(production, 'date_planned_start') and production.date_planned_start:
            reference_date = production.date_planned_start
            _logger.debug(f"Using date_planned_start as reference: {reference_date}")

        # Prioridad 3: create_date (fecha de creación)
        elif hasattr(production, 'create_date') and production.create_date:
            reference_date = production.create_date
            _logger.debug(f"Using create_date as reference: {reference_date}")

        else:
            _logger.warning(f"No suitable reference date found for MO {production.name}")

        return reference_date

    #  PRECIO INTELIGENTE: Jerarquía de fuentes para obtener precio más confiable
    def _get_reliable_product_cost(self, product, move_line=None, date=None, mrp_workorder_mode=False):
        """Obtiene el costo más confiable usando jerarquía de fuentes

        Args:
            product: Producto para obtener el costo
            move_line: Línea de movimiento específica (opcional)
            date: Fecha de referencia para búsqueda histórica (ej: date_start de la MO)
            mrp_workorder_mode: Si True, replica exactamente la lógica de mrp_workorder
        """

        _logger.debug(f"🎯 Getting reliable cost for product: {product.name} (mrp_workorder_mode: {mrp_workorder_mode}, date: {date})")

        # MODO COMPATIBILIDAD: Replicar exactamente mrp_workorder con contexto temporal
        if mrp_workorder_mode:
            #  INVESTIGACIÓN: mrp_workorder podría usar price_unit del movimiento
            if move_line and hasattr(move_line, 'price_unit') and move_line.price_unit > 0:
                cost = move_line.price_unit
                _logger.info(f"💰 MRP_WORKORDER MODE - Using move_line.price_unit: {cost} for {product.name}")
                return cost

            # Obtener costos base
            avg_cost = getattr(product, 'avg_cost', 0)
            standard_price = product.with_company(self.env.company).standard_price or 0

            _logger.debug(f"📊 Base prices for {product.name}: standard_price={standard_price}, avg_cost={avg_cost}")

            # Buscar valoración histórica usando fecha de referencia
            valuation_cost = self._get_historical_valuation_cost(product, date)

            #  LÓGICA MEJORADA: Usar valoración histórica cuando existe fecha de referencia
            if valuation_cost > 0:
                cost = valuation_cost
                _logger.info(f"✅ MRP_WORKORDER TEMPORAL - Using historical valuation_cost: {cost} for {product.name} at {date}")
            else:
                # Fallback a standard_price
                cost = standard_price
                _logger.info(f"✅ MRP_WORKORDER TEMPORAL - Using standard_price: {cost} for {product.name} (no historical valuation)")

            # Debug info detallado
            _logger.debug(f" Price sources for {product.name} at {date}:")
            _logger.debug(f"  - standard_price: {standard_price}")
            _logger.debug(f"  - avg_cost: {avg_cost}")
            _logger.debug(f"  - historical_valuation_cost: {valuation_cost}")
            _logger.debug(f"  - SELECTED: {cost}")

            return cost

        # MODO AVANZADO: Jerarquía completa (comportamiento original)
        # 1. PRIORIDAD MÁXIMA: Precio desde el movimiento específico (más preciso)
        if move_line and hasattr(move_line, 'price_unit') and move_line.price_unit > 0:
            cost = move_line.price_unit
            _logger.debug(f"Using move price_unit: {cost} for {product.name}")
            return cost

        # 1.5. ALTA PRIORIDAD: standard_price (como en mrp_workorder)
        if hasattr(product, 'standard_price') and product.standard_price > 0:
            cost = product.standard_price
            _logger.debug(f"Using standard_price: {cost} for {product.name}")
            return cost

        # 2. MUY ALTA PRIORIDAD: Historial de costos (product.cost.history) - PRIORIDAD ELEVADA
        cost_history = self._get_cost_from_history(product, days=60)  # Ventana más amplia
        if cost_history and cost_history > 0:
            _logger.debug(f"Using cost history: {cost_history} for {product.name}")
            return cost_history

        # 3. ALTA PRIORIDAD: Último precio de compra reciente (30 días)
        recent_purchase = self._get_recent_purchase_price(product, days=30)
        if recent_purchase and recent_purchase > 0:
            _logger.debug(f"Using recent purchase price: {recent_purchase} for {product.name}")
            return recent_purchase

        # 4. MEDIA PRIORIDAD: Costo promedio ponderado si está disponible
        if hasattr(product, 'avg_cost') and product.avg_cost > 0:
            _logger.debug(f"Using avg_cost: {product.avg_cost} for {product.name}")
            return product.avg_cost

        # 5. PRIORIDAD BAJA: Standard price como fallback
        standard_cost = product.standard_price or 0
        _logger.debug(f"Using standard_price fallback: {standard_cost} for {product.name}")
        return standard_cost

    def _get_cost_from_history(self, product, days=60):
        """Obtiene el costo más reciente del historial de costos del producto"""
        try:
            # Verificar si el modelo existe
            if 'product.cost.history' not in self.env:
                return None

            cutoff_date = fields.Datetime.now() - timedelta(days=days)

            # Buscar el registro más reciente con costo válido
            cost_history = self.env['product.cost.history'].search([
                ('product_id', '=', product.id),
                ('date', '>=', cutoff_date),
                '|', '|',
                ('old_cost', '>', 0),        # PRIORIDAD: old_cost (usado por vista nativa)
                ('new_cost', '>', 0),
                ('operation_cost', '>', 0)
            ], order='date desc', limit=1)

            if cost_history:
                # PRIORIDAD MÁXIMA: old_cost (coincide con vista nativa de Odoo)
                if cost_history.old_cost > 0:
                    cost_to_use = cost_history.old_cost
                    _logger.info(f"🔍 COST HISTORY (old_cost) found for {product.name}: {cost_to_use} (reference: {cost_history.reference})")
                    return cost_to_use
                # Fallback a new_cost o operation_cost
                elif cost_history.new_cost > 0:
                    cost_to_use = cost_history.new_cost
                    _logger.info(f"🔍 COST HISTORY (new_cost) found for {product.name}: {cost_to_use} (reference: {cost_history.reference})")
                    return cost_to_use
                elif cost_history.operation_cost > 0:
                    cost_to_use = cost_history.operation_cost
                    _logger.info(f"🔍 COST HISTORY (operation_cost) found for {product.name}: {cost_to_use} (reference: {cost_history.reference})")
                    return cost_to_use

            # Si no hay registros recientes, buscar el más reciente sin restricción de fecha
            latest_cost_history = self.env['product.cost.history'].search([
                ('product_id', '=', product.id),
                '|', '|',
                ('old_cost', '>', 0),
                ('new_cost', '>', 0),
                ('operation_cost', '>', 0)
            ], order='date desc', limit=1)

            if latest_cost_history:
                # Misma lógica de prioridad para registros más antiguos
                if latest_cost_history.old_cost > 0:
                    cost_to_use = latest_cost_history.old_cost
                    _logger.info(f"🔍 COST HISTORY (old_cost, older) found for {product.name}: {cost_to_use} (reference: {latest_cost_history.reference})")
                    return cost_to_use
                elif latest_cost_history.new_cost > 0:
                    cost_to_use = latest_cost_history.new_cost
                    _logger.info(f"🔍 COST HISTORY (new_cost, older) found for {product.name}: {cost_to_use} (reference: {latest_cost_history.reference})")
                    return cost_to_use
                elif latest_cost_history.operation_cost > 0:
                    cost_to_use = latest_cost_history.operation_cost
                    _logger.info(f"🔍 COST HISTORY (operation_cost, older) found for {product.name}: {cost_to_use} (reference: {latest_cost_history.reference})")
                    return cost_to_use

        except Exception as e:
            _logger.warning(f"Error accessing product.cost.history for {product.name}: {e}")

        return None

    def _get_recent_purchase_price(self, product, days=30):
        """Obtiene el precio de compra más reciente dentro de X días"""
        try:
            cutoff_date = fields.Datetime.now() - timedelta(days=days)

            # Estrategia 1: Buscar en purchase.order.line con campos correctos
            try:
                # Intentar con diferentes variantes del campo de fecha
                date_field_options = ['date_order', 'create_date', 'date_planned']

                for date_field in date_field_options:
                    try:
                        recent_purchase = self.env['purchase.order.line'].search([
                            ('product_id', '=', product.id),
                            (f'order_id.{date_field}', '>=', cutoff_date),
                            ('order_id.state', 'in', ['purchase', 'done']),
                            ('price_unit', '>', 0)
                        ], order=f'order_id.{date_field} desc', limit=1)

                        if recent_purchase:
                            _logger.debug(f"Found recent purchase using {date_field}: {recent_purchase.price_unit} for {product.name}")
                            return recent_purchase.price_unit
                    except Exception:
                        continue  # Intentar con el siguiente campo

            except Exception as e:
                _logger.debug(f"Purchase order line search failed: {e}")

            # Estrategia 2: Buscar en stock.move para recepciones recientes
            try:
                recent_receipt = self.env['stock.move'].search([
                    ('product_id', '=', product.id),
                    ('date', '>=', cutoff_date),
                    ('location_dest_id.usage', '=', 'internal'),  # Movimientos entrantes
                    ('location_id.usage', '!=', 'internal'),      # Desde ubicación externa
                    ('state', '=', 'done'),
                    ('price_unit', '>', 0)
                ], order='date desc', limit=1)

                if recent_receipt:
                    _logger.debug(f"Found recent receipt: {recent_receipt.price_unit} for {product.name}")
                    return recent_receipt.price_unit
            except Exception as e:
                _logger.debug(f"Stock move search failed: {e}")

            # Estrategia 3: Buscar en stock.valuation.layer (más confiable para costos)
            try:
                recent_valuation = self.env['stock.valuation.layer'].search([
                    ('product_id', '=', product.id),
                    ('create_date', '>=', cutoff_date),
                    ('quantity', '>', 0),  # Solo entradas
                    ('unit_cost', '>', 0)
                ], order='create_date desc', limit=1)

                if recent_valuation:
                    _logger.debug(f"Found recent valuation: {recent_valuation.unit_cost} for {product.name}")
                    return recent_valuation.unit_cost
            except Exception as e:
                _logger.debug(f"Valuation layer search failed: {e}")

            # Estrategia 4: Ya manejada por _get_cost_from_history() con mayor prioridad

        except Exception as e:
            _logger.warning(f"Error getting recent purchase price for {product.name}: {e}")

        return None

    def debug_pricing_sources(self, product):
        """Método para diagnosticar qué fuentes de precio están disponibles para un producto"""
        sources = {}

        # 1. Move price (requiere move_line)
        sources['move_price'] = 'N/A (requires move_line)'

        # 2. Cost History (detallado)
        try:
            if 'product.cost.history' in self.env:
                latest_history = self.env['product.cost.history'].search([
                    ('product_id', '=', product.id)
                ], order='date desc', limit=1)

                if latest_history:
                    sources['cost_history_old_cost'] = latest_history.old_cost or 'Empty'
                    sources['cost_history_new_cost'] = latest_history.new_cost or 'Empty'
                    sources['cost_history_operation_cost'] = latest_history.operation_cost or 'Empty'
                    sources['cost_history_reference'] = latest_history.reference
                    sources['cost_history_date'] = str(latest_history.date)
                else:
                    sources['cost_history_old_cost'] = 'No records found'
            else:
                sources['cost_history_old_cost'] = 'Model not available'
        except Exception as e:
            sources['cost_history_old_cost'] = f'Error: {e}'

        # Resultado de _get_cost_from_history
        cost_history = self._get_cost_from_history(product, days=60)
        sources['cost_history_final'] = cost_history if cost_history else 'Not found'

        # 3. Recent purchase
        recent_purchase = self._get_recent_purchase_price(product, days=30)
        sources['recent_purchase'] = recent_purchase if recent_purchase else 'Not found'

        # 4. Average cost
        sources['avg_cost'] = getattr(product, 'avg_cost', 'Field not available')

        # 5. Standard price
        sources['standard_price'] = product.standard_price or 0

        # Final usado por _get_reliable_product_cost
        final_cost = self._get_reliable_product_cost(product)
        sources['final_used'] = final_cost

        _logger.info(f"🔍 PRICING DEBUG for {product.name}: {sources}")
        return sources

    def _get_safe_currency_info(self, production):
        """Obtiene información de moneda de forma segura con fallbacks"""
        try:
            if production and production.company_id and production.company_id.currency_id:
                currency = production.company_id.currency_id

                if currency.exists():
                    return {
                        'company_currency': {
                            'id': currency.id,
                            'name': currency.name or 'USD',
                            'symbol': currency.symbol or '$',
                            'position': getattr(currency, 'position', 'before') or 'before',
                        },
                        'currency_symbol': currency.symbol or '$',
                        'currency_name': currency.name or 'USD',
                    }

            # Fallback seguro
            return {
                'company_currency': {
                    'id': False,
                    'name': 'USD',
                    'symbol': '$',
                    'position': 'before',
                },
                'currency_symbol': '$',
                'currency_name': 'USD',
            }

        except Exception as e:
            _logger.error(f"Error loading currency info: {e}")
            return {
                'company_currency': {
                    'id': False,
                    'name': 'USD',
                    'symbol': '$',
                    'position': 'before',
                },
                'currency_symbol': '$',
                'currency_name': 'USD',
            }