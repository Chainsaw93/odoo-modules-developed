from odoo import models, api, _
from odoo.exceptions import UserError

class StockBarcodeValidation(models.Model):
    _inherit = 'stock.picking'

    @api.model
    def _get_stock_barcode_data(self):
        """Override para incluir validación de series en barcode"""
        result = super()._get_stock_barcode_data()
        
        # Añadir configuración de validación de series
        result.update({
            'serial_validation_enabled': True,
            'validation_service': 'stock.serial.validation.service'
        })
        
        return result

    def _process_barcode_serial_number(self, barcode, product_id):
        """
        Procesar escaneo de código de barras para números de serie
        """
        if not product_id:
            raise UserError(_('Debe seleccionar un producto primero'))

        product = self.env['product.product'].browse(product_id)
        if not product.tracking == 'serial':
            raise UserError(_('El producto no requiere números de serie'))

        # Validar usando servicio central
        validation_service = self.env['stock.serial.validation.service']
        validation_result = validation_service.validate_serial_number(
            product_id=product_id,
            serial_number=barcode,
            picking_id=self.id,
            context_type='barcode_scan'
        )

        if not validation_result['valid']:
            raise UserError(validation_result['message'])

        return self._create_or_update_move_line_for_serial(product_id, barcode)

    def _create_or_update_move_line_for_serial(self, product_id, serial_number):
        """Crear o actualizar línea de movimiento para número de serie"""
        # Buscar línea existente sin número de serie para este producto
        move_line = self.move_line_ids.filtered(
            lambda l: l.product_id.id == product_id and not l.lot_name and not l.lot_id
        )[:1]

        if move_line:
            # Actualizar línea existente
            move_line.write({
                'lot_name': serial_number,
                'qty_done': 1.0
            })
        else:
            # Crear nueva línea
            move = self.move_ids.filtered(lambda m: m.product_id.id == product_id)[:1]
            if not move:
                raise UserError(_('No se encontró movimiento para este producto'))

            move_line = self.env['stock.move.line'].create({
                'move_id': move.id,
                'picking_id': self.id,
                'product_id': product_id,
                'lot_name': serial_number,
                'qty_done': 1.0,
                'location_id': move.location_id.id,
                'location_dest_id': move.location_dest_id.id,
                'product_uom_id': move.product_uom.id,
            })

        return move_line

class StockMoveLineBarcodeValidation(models.Model):
    _inherit = 'stock.move.line'

    def on_barcode_scanned(self, barcode):
        """
        Override para manejar escaneo de códigos de barras con validación
        """
        if self.product_id and self.product_id.tracking == 'serial':
            return self.picking_id._process_barcode_serial_number(barcode, self.product_id.id)
        
        return super().on_barcode_scanned(barcode)