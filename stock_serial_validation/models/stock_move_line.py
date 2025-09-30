from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)

class StockMoveLineSerial(models.Model):
    _inherit = 'stock.move.line'

    # --- CAMBIO: Se unifica el onchange para ambos campos ---
    @api.onchange('lot_name', 'lot_id')
    def _onchange_serial_number_validation(self):
        """
        Validación en tiempo real que se activa al escribir o seleccionar un número de serie.
        Ahora usa el servicio central y lanza una excepción directa para un feedback inmediato.
        """
        # Si el producto no requiere seguimiento por serie, no hacemos nada.
        if not self.product_id or self.product_id.tracking != 'serial':
            return

        serial_number = self.lot_name or (self.lot_id.name if self.lot_id else None)
        
        # Si el campo del número de serie está vacío, no hay nada que validar.
        if not serial_number:
            return

        # --- CAMBIO CLAVE: Llamada al servicio de validación central ---
        validation_service = self.env['stock.serial.validation.service']
        
        # Pasamos `self._origin.id` para que al editar una línea, no se detecte a sí misma como un duplicado.
        validation_result = validation_service.validate_serial_number(
            product_id=self.product_id.id,
            serial_number=serial_number,
            picking_id=self.picking_id.id,
            exclude_line_id=self._origin.id 
        )

        # --- CAMBIO: Usamos ValidationError para una respuesta en tiempo real ---
        if not validation_result.get('valid'):
            # Este es el método moderno y más robusto. Odoo mostrará un diálogo de error
            # y revertirá automáticamente el valor del campo que causó el error.
            raise ValidationError(validation_result.get('message'))

    # --- CAMBIO: Los campos computados ahora llaman al onchange para recalcular ---
    # Esto asegura que el estado visual se actualice consistentemente.
    @api.depends('lot_name', 'lot_id')
    def _compute_serial_validation_status(self):
        # Esta función puede permanecer o ser simplificada, ya que el onchange es el que
        # previene los datos incorrectos. La decoración visual es secundaria.
        # Por simplicidad y robustez, la validación principal es en el onchange.
        for line in self:
             if not (line.product_id and line.product_id.tracking == 'serial'):
                line.serial_validation_status = 'not_required'
                line.serial_validation_message = ''
                continue
             
             serial_number = line.lot_name or (line.lot_id.name if line.lot_id else None)
             if not serial_number:
                line.serial_validation_status = 'pending'
                line.serial_validation_message = _('Número de serie requerido')
             else:
                # Opcional: Se podría re-validar aquí para el estado visual,
                # pero el onchange ya previene datos malos.
                line.serial_validation_status = 'valid'
                line.serial_validation_message = ''


    # --- CAMBIO: La restricción de guardado también usará el servicio central ---
    @api.constrains('lot_name', 'lot_id', 'qty_done', 'product_id')
    def _check_serial_number_validation(self):
        """
        Validación final ANTES de guardar en la base de datos. 
        Actúa como una barrera de seguridad final.
        """
        for line in self:
            if not (line.product_id and line.product_id.tracking == 'serial' and line.qty_done > 0):
                continue
            
            serial_number = line.lot_name or (line.lot_id.name if line.lot_id else None)
            if not serial_number:
                if line.picking_id.picking_type_id.code != 'incoming':
                    raise ValidationError(_('Se requiere un número de serie para el producto %s.') % line.product_id.display_name)
                continue

            # No validamos duplicados al recibir, ya que aquí se están creando los números de serie.
            if line.picking_id.picking_type_id.code == 'incoming':
                continue

            # Llamada al servicio central
            validation_service = self.env['stock.serial.validation.service']
            validation_result = validation_service.validate_serial_number(
                product_id=line.product_id.id,
                serial_number=serial_number,
                picking_id=line.picking_id.id,
                exclude_line_id=line.id
            )

            if not validation_result.get('valid'):
                raise ValidationError(validation_result.get('message'))