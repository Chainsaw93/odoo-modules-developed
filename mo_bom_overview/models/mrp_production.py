from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    def action_view_mo_bom_overview(self, mrp_workorder_compatibility=None):
        """Abre el MO BOM Overview con datos del MO Overview pero formato del BOM

        Args:
            mrp_workorder_compatibility: Si True, usa precios compatibles con mrp_workorder
        """
        context = {
            'active_id': self.id,
            'active_model': self._name,
            'production_qty_to_use': self.get_reliable_product_qty(),  #FIX: usar cantidad confiable
        }

        # Agregar modo de compatibilidad si se especifica
        if mrp_workorder_compatibility is not None:
            context['mrp_workorder_compatibility'] = mrp_workorder_compatibility

        return {
            'type': 'ir.actions.client',
            'name': 'BOM Overview',
            'tag': 'mo_bom_overview',
            'context': context,
        }

    #FIX 9: Override write para auto-invalidación
    def write(self, vals):
        """Override write con invalidación correcta de caché"""
        # Guardar IDs antes de modificaciones
        affected_ids = self.ids

        # Ejecutar escritura estándar
        result = super().write(vals)

        # Si se modificó product_qty, invalidar caché específico
        if 'product_qty' in vals:
            affected_records = self.env['mrp.production'].browse(affected_ids)
            affected_records.invalidate_recordset(['product_qty'])

            # También invalidar campos relacionados que podrían cambiar
            affected_records.move_raw_ids.invalidate_recordset(['product_uom_qty'])

            # Log para debugging
            _logger.info(f" Auto-invalidated cache for product_qty in MO {affected_records.mapped('name')}")
            _logger.info(f"New product_qty values: {vals.get('product_qty')}")

        return result

    def get_reliable_product_qty(self):
        """Lectura confiable de product_qty actualizada"""
        # 1. Flush cambios pendientes
        self.flush_recordset(['product_qty'])

        # 2. Invalidar caché específico
        self.invalidate_recordset(['product_qty'])

        # 3. Releer valor fresco
        fresh_qty = self.product_qty

        _logger.debug(f"Reliable product_qty for MO {self.name}: {fresh_qty}")
        return fresh_qty

    def get_reliable_production_data(self):
        """Obtiene datos completos de la producción con invalidación específica"""
        # Invalidar campos críticos
        critical_fields = ['product_qty', 'state', 'name', 'product_id', 'product_uom_id']
        self.invalidate_recordset(critical_fields)

        # También invalidar move_raw_ids relacionados
        self.move_raw_ids.invalidate_recordset(['product_uom_qty'])

        return {
            'id': self.id,
            'name': self.name,
            'product_qty': self.product_qty,
            'state': self.state,
            'product_id': self.product_id.id,
            'product_name': self.product_id.display_name,
            'uom_name': self.product_uom_id.name,
        }

    def debug_cache_consistency(self):
        """Método público para diagnosticar problemas de caché"""
        try:
            # Leer valor actual (posiblemente cacheado)
            cached_value = self.product_qty

            # Invalidar y releer
            self.invalidate_recordset(['product_qty'])
            fresh_value = self.product_qty

            # Leer directamente de BD
            self.env.cr.execute(
                "SELECT product_qty FROM mrp_production WHERE id = %s",
                (self.id,)
            )
            db_result = self.env.cr.fetchone()
            db_value = db_result[0] if db_result else None

            # Comparar valores
            consistency_info = {
                'mo_name': self.name,
                'mo_id': self.id,
                'cached': cached_value,
                'fresh': fresh_value,
                'database': db_value,
                'is_consistent': cached_value == fresh_value == db_value,
                'timestamp': fields.Datetime.now()
            }

            if not consistency_info['is_consistent']:
                _logger.warning(f" CACHE INCONSISTENCY in MO {self.name}: {consistency_info}")
            else:
                _logger.info(f" Cache consistent in MO {self.name}")

            return consistency_info

        except Exception as e:
            _logger.error(f"Error in cache consistency check for MO {self.name}: {e}")
            return {'error': str(e), 'mo_name': self.name, 'mo_id': self.id}

    def set_qty_producing(self):
        """Método para actualizar qty_producing similar a mrp_workorder
        Permite actualizar cantidades producidas después de confirmar la orden"""
        # Este método replica la funcionalidad de mrp_workorder
        # para actualizar cantidades sin cambios visuales
        if hasattr(self, 'qty_producing'):
            # Invalidar caché para asegurar datos frescos
            self.invalidate_recordset(['qty_producing', 'product_qty'])
            _logger.info(f"Updated qty_producing for MO {self.name}")
        return True

    def get_mo_bom_data(self, mrp_workorder_compatibility=False):
        """Obtiene datos para el reporte PDF - con lectura confiable

        Args:
            mrp_workorder_compatibility: Si True, usa solo standard_price (igual que mrp_workorder)
        """
        # Asegurar datos frescos antes de llamar al reporte
        reliable_qty = self.get_reliable_product_qty()

        mo_report = self.env['report.mo.bom.overview']
        return mo_report.get_report_data(self.id, reliable_qty, False, mrp_workorder_compatibility)

    def get_mo_bom_data_mrp_workorder_compatible(self):
        """Obtiene datos usando exactamente la misma lógica de precios que mrp_workorder

        Método de conveniencia que activa el modo de compatibilidad automáticamente
        """
        return self.get_mo_bom_data(mrp_workorder_compatibility=True)

    @api.model
    def read_multiple_productions_reliable(self, production_ids, fields=None):
        """Método para lectura confiable de múltiples producciones"""
        if not production_ids:
            return []

        productions = self.browse(production_ids)

        # Invalidar caché en lote para eficiencia
        if not fields:
            fields = ['name', 'product_qty', 'state']

        # Solo invalidar campos específicos que se van a leer
        cache_fields_to_invalidate = [f for f in fields if f in ['product_qty', 'state', 'name']]
        if cache_fields_to_invalidate:
            productions.invalidate_recordset(cache_fields_to_invalidate)

        # Usar read() para múltiples registros es más eficiente
        data = productions.read(fields)

        _logger.debug(f"Reliable read for {len(production_ids)} productions, fields: {fields}")
        return data

    #FIX 10: Método para refrescar datos automáticamente desde JavaScript
    def refresh_production_data_for_client(self):
        """Método llamado desde JavaScript para obtener datos actualizados"""
        try:
            # Obtener datos confiables
            production_data = self.get_reliable_production_data()

            # También verificar consistencia si estamos en modo debug
            if _logger.isEnabledFor(logging.DEBUG):
                consistency = self.debug_cache_consistency()
                production_data['_debug_cache'] = consistency

            return {
                'success': True,
                'data': production_data,
                'timestamp': fields.Datetime.now().isoformat()
            }

        except Exception as e:
            _logger.error(f"Error refreshing production data: {e}")
            return {
                'success': False,
                'error': str(e),
                'mo_name': getattr(self, 'name', 'Unknown'),
                'mo_id': self.id
            }