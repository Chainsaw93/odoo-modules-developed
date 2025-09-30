# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)

class LoanResolutionWizard(models.TransientModel):
    _name = 'loan.resolution.wizard'
    _description = 'Asistente para Resolución de Préstamos'

    # Información del préstamo
    picking_id = fields.Many2one(
        'stock.picking',
        string='Préstamo Original',
        required=True,
        readonly=True
    )
    
    partner_id = fields.Many2one(
        'res.partner',
        related='picking_id.loaned_to_partner_id',
        string='Cliente',
        readonly=True
    )
    
    loan_date = fields.Datetime(
        related='picking_id.date_done',
        string='Fecha del Préstamo',
        readonly=True
    )
    
    # Configuración de la resolución
    resolution_date = fields.Datetime(
        string='Fecha de Resolución',
        default=fields.Datetime.now,
        required=True
    )
    
    notes = fields.Text(
        string='Notas de Resolución',
        help="Observaciones sobre la resolución del préstamo"
    )
    
    # Líneas de resolución
    resolution_line_ids = fields.One2many(
        'loan.resolution.wizard.line',
        'wizard_id',
        string='Productos a Resolver'
    )
    
    # Campos calculados automáticamente
    total_sale_amount = fields.Monetary(
        string='Total Venta',
        compute='_compute_totals',
        currency_field='currency_id',
        help="Monto total de productos que serán vendidos"
    )
    
    total_return_items = fields.Integer(
        string='Items a Devolver',
        compute='_compute_totals',
        help="Número de items que serán devueltos"
    )
    
    total_keep_loan_items = fields.Integer(
        string='Items que Permanecen en Préstamo',
        compute='_compute_totals',
        help="Número de items que siguen en préstamo"
    )
    
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        default=lambda self: self.env.company.currency_id
    )
    
    # Flags de estado
    has_sales = fields.Boolean(
        string='Tiene Ventas',
        compute='_compute_totals'
    )
    
    has_returns = fields.Boolean(
        string='Tiene Devoluciones',
        compute='_compute_totals'
    )
    
    has_continued_loans = fields.Boolean(
        string='Préstamos Continuos',
        compute='_compute_totals'
    )

    @api.model
    def default_get(self, fields_list):
        """Poblar automáticamente las líneas de resolución desde los detalles de seguimiento"""
        _logger.info("Iniciando default_get para loan.resolution.wizard...")
        res = super().default_get(fields_list)
        
        picking_id = self.env.context.get('active_id')
        if not picking_id:
            _logger.warning("No se encontró picking_id en el contexto")
            return res
            
        picking = self.env['stock.picking'].browse(picking_id)
        if not picking.exists() or not picking.is_loan:
            _logger.warning(f"Picking {picking_id} no existe o no es un préstamo")
            return res
        
        _logger.info(f"Buscando detalles de seguimiento para picking {picking.name}")
        
        # Buscar detalles de seguimiento existentes y asegurar que los tenemos
        tracking_details = self.env['loan.tracking.detail'].search([
            ('picking_id', '=', picking.id),
            ('status', 'in', ['active', 'pending_resolution'])
        ])
        
        _logger.info(f"Encontrados {len(tracking_details)} detalles de seguimiento activos")
        
        resolution_lines = []
        
        # Si hay detalles de seguimiento, usarlos
        if tracking_details:
            for detail in tracking_details:
                # Verificar que el detalle existe y está activo
                if not detail.exists() or detail.status not in ['active', 'pending_resolution']:
                    _logger.warning(
                        f"Detalle de seguimiento {detail.id} no válido para producto {detail.product_id.name}. "
                        f"Estado: {detail.status}"
                    )
                    continue
                
                # Crear línea del wizard con referencia al tracking detail
                line_vals = {
                    'tracking_detail_id': detail.id,
                    'product_id': detail.product_id.id,
                    'lot_id': detail.lot_id.id if detail.lot_id else False,
                    'loaned_qty': detail.quantity,
                    'qty_to_resolve': detail.quantity,
                    'resolution_type': 'keep_loan',
                    'unit_price': detail.product_id.list_price,
                }
                
                # Crear línea y verificar que se creó correctamente
                resolution_lines.append((0, 0, line_vals))
                _logger.info(
                    f"Línea preparada desde tracking para producto {detail.product_id.name} "
                    f"con cantidad {detail.quantity}, tracking_detail_id={detail.id}"
                )
        else:
            # Si no hay detalles, crearlos desde los movimientos
            for move in picking.move_ids_without_package.filtered(lambda m: m.state == 'done'):
                qty_done = sum(move.move_line_ids.mapped('qty_done'))
                if qty_done <= 0:
                    continue
                    
                # Crear tracking detail
                tracking_detail = self.env['loan.tracking.detail'].create({
                    'picking_id': picking.id,
                    'product_id': move.product_id.id,
                    'quantity': qty_done,  # Guardar qty_done como quantity en tracking
                    'status': 'active',
                    'loan_date': picking.date_done or fields.Datetime.now(),
                    'original_cost': move.product_id.standard_price,
                })
                
                line_vals = {
                    'tracking_detail_id': tracking_detail.id,
                    'product_id': move.product_id.id,
                    'loaned_qty': tracking_detail.quantity,  # Usar quantity del tracking
                    'qty_to_resolve': tracking_detail.quantity,
                    'resolution_type': 'keep_loan',
                    'unit_price': move.product_id.list_price,
                }
                resolution_lines.append((0, 0, line_vals))
                _logger.info(f"Línea preparada desde movimiento para producto {move.product_id.name} con cantidad {tracking_detail.quantity}")
        
        res['resolution_line_ids'] = resolution_lines
        return res

    def _create_tracking_from_moves(self, picking):
        """Crear tracking details directamente desde movimientos validados"""
        details = []
        
        for move in picking.move_ids_without_package.filtered(lambda m: m.state == 'done'):
            if move.product_id.tracking == 'serial':
                # Para productos con serie
                for move_line in move.move_line_ids:
                    if move_line.lot_id and move_line.qty_done > 0:
                        detail = self.env['loan.tracking.detail'].sudo().create({
                            'picking_id': picking.id,
                            'product_id': move.product_id.id,
                            'lot_id': move_line.lot_id.id,
                            'quantity': move_line.qty_done,
                            'status': 'active',
                            'loan_date': picking.date_done or fields.Datetime.now(),
                            'original_cost': move.product_id.standard_price,
                        })
                        details.append(detail)
            else:
                # Para productos sin serie
                qty_done = sum(move.move_line_ids.mapped('qty_done'))
                if qty_done > 0:
                    detail = self.env['loan.tracking.detail'].sudo().create({
                        'picking_id': picking.id,
                        'product_id': move.product_id.id,
                        'quantity': qty_done,
                        'status': 'active',
                        'loan_date': picking.date_done or fields.Datetime.now(),
                        'original_cost': move.product_id.standard_price,
                    })
                    details.append(detail)
        
        return self.env['loan.tracking.detail'].browse([d.id for d in details])

    @api.depends('resolution_line_ids.resolution_type', 'resolution_line_ids.qty_to_resolve', 'resolution_line_ids.unit_price')
    def _compute_totals(self):
        """Calcular totales basados en las decisiones de resolución"""
        for wizard in self:
            total_sale = 0.0
            return_items = 0
            keep_loan_items = 0
            has_sales = False
            has_returns = False
            has_continued = False
            
            for line in wizard.resolution_line_ids:
                if line.resolution_type == 'buy':
                    total_sale += line.qty_to_resolve * line.unit_price
                    has_sales = True
                elif line.resolution_type == 'return':
                    return_items += 1 if line.product_id.tracking == 'serial' else line.qty_to_resolve
                    has_returns = True
                elif line.resolution_type == 'keep_loan':
                    keep_loan_items += 1 if line.product_id.tracking == 'serial' else line.qty_to_resolve
                    has_continued = True
            
            wizard.total_sale_amount = total_sale
            wizard.total_return_items = return_items
            wizard.total_keep_loan_items = keep_loan_items
            wizard.has_sales = has_sales
            wizard.has_returns = has_returns
            wizard.has_continued_loans = has_continued

    def _process_resolution(self):
        """Procesar la resolución del préstamo"""
        self.ensure_one()
        
        _logger.info(f"Iniciando proceso de resolución para préstamo {self.picking_id.name}")
        
        # Validaciones previas
        self._validate_resolution()
        
        results = {
            'sale_order': None,
            'return_picking': None,
            'continued_details': []
        }
        
        try:
            # 1. Cambiar estado a 'resolving' primero
            self.picking_id.write({'loan_state': 'resolving'})
            
            # 2. Procesar ventas
            if self.has_sales:
                _logger.info("Procesando ventas...")
                # Verificar líneas de venta antes de procesar
                sale_lines = self.resolution_line_ids.filtered(lambda l: l.resolution_type == 'buy')
                _logger.info(f"Líneas para venta encontradas: {len(sale_lines)}")
                for line in sale_lines:
                    _logger.info(
                        f"Preparando venta: Producto={line.product_id.name}, "
                        f"Tracking Detail={line.tracking_detail_id.id if line.tracking_detail_id else 'None'}"
                    )
                results['sale_order'] = self._process_sales()
            else:
                _logger.info("No hay ventas para procesar")
        
            # 3. Procesar devoluciones
            if self.has_returns:
                _logger.info("Procesando devoluciones...")
                results['return_picking'] = self._process_returns()
        
            # 4. Mantener préstamos continuos
            if self.has_continued_loans:
                results['continued_details'] = self._process_continued_loans()
        
            # 5. Determinar estado final basado en las decisiones
            if self.has_continued_loans:
                self.picking_id.write({'loan_state': 'partially_resolved'})
            elif self.has_returns:
                # Si hay devoluciones, mantener en partially_resolved hasta que se validen
                self.picking_id.write({'loan_state': 'partially_resolved'})
            else:
                # Solo si no hay préstamos continuos ni devoluciones pendientes, completar
                self.picking_id.write({'loan_state': 'partially_resolved'})
                self.picking_id.write({'loan_state': 'completed'})
        
            return self._return_resolution_results(results)
            
        except Exception as e:
            _logger.error(f"Error en resolución de préstamo: {str(e)}")
            raise UserError(_(
                f"Error al procesar la resolución del préstamo: {str(e)}"
            ))

    def _validate_resolution(self):
        """Validar que la resolución es consistente"""
        if not self.resolution_line_ids:
            raise UserError(_("No hay productos para resolver."))
        
        # Validar cantidades y consistencia
        for line in self.resolution_line_ids:
            tracking_detail = line.tracking_detail_id
            if not tracking_detail:
                continue
            
            if line.qty_to_resolve > tracking_detail.quantity:
                raise UserError(_(
                    f"No se puede resolver más cantidad de la prestada para {line.product_id.name}. "
                    f"Prestado: {tracking_detail.quantity}, "
                    f"Intentando resolver: {line.qty_to_resolve}"
                ))
                
            if tracking_detail.status not in ['active', 'pending_resolution']:
                raise UserError(_(
                    f"El producto {line.product_id.name} no está disponible para resolución. "
                    f"Estado actual: {tracking_detail.status}"
                ))

    def _process_sales(self):
        """Procesar productos que el cliente decide comprar"""
        _logger.info("Iniciando procesamiento de ventas...")
        
        # Obtener líneas de venta y verificar que existan
        sale_lines = self.resolution_line_ids.filtered(
            lambda l: l.resolution_type == 'buy'
        )
        
        _logger.info(f"Encontradas {len(sale_lines)} líneas para venta")
        
        # Validar que todas las líneas tengan tracking detail
        invalid_lines = sale_lines.filtered(lambda l: not l.tracking_detail_id)
        if invalid_lines:
            raise UserError(_(
                "Las siguientes líneas no tienen detalle de seguimiento:\n" + 
                "\n".join([f"- {l.product_id.name}" for l in invalid_lines])
            ))
            
        # Validar estado de tracking details
        invalid_states = sale_lines.filtered(
            lambda l: l.tracking_detail_id.status not in ['active', 'pending_resolution']
        )
        if invalid_states:
            raise UserError(_(
                "Los siguientes productos no están en estado válido para venta:\n" + 
                "\n".join([
                    f"- {l.product_id.name} (Estado: {l.tracking_detail_id.status})" 
                    for l in invalid_states
                ])
            ))
            
        _logger.info("Validación de líneas completada, procesando venta...")
        
        if not sale_lines:
            _logger.warning("No se encontraron líneas para venta")
            return None
        
        # Crear orden de venta
        sale_order = self._create_sale_order(sale_lines)
        
        # Guardar referencia en el picking original
        self.picking_id.write({
            'loan_sale_order': sale_order.id
        })
        
        # Actualizar detalles de seguimiento
        for line in sale_lines:
            if not line.tracking_detail_id:
                _logger.error(f"No se encontró detalle de seguimiento para la línea con producto {line.product_id.name}")
                continue
            
            # Encontrar la línea de venta correspondiente
            sale_line = sale_order.order_line.filtered(
                lambda sol: (
                    sol.product_id == line.product_id and 
                    (not line.lot_id or line.lot_id.name in (sol.name or ''))
                )
            )
            
            if not sale_line:
                _logger.error(f"No se encontró línea de venta para el producto {line.product_id.name}")
                continue
            
            tracking_detail = line.tracking_detail_id
            if not tracking_detail or not tracking_detail.exists():
                raise UserError(_(
                    f"No se encontró el detalle de seguimiento para el producto {line.product_id.name}. "
                    f"Por favor, actualice el wizard y vuelva a intentarlo."
                ))

            try:
                # Marcar como vendido usando sudo() para asegurar permisos
                tracking_detail.sudo().with_context(skip_check=True).write({
                    'status': 'sold',
                    'resolution_date': fields.Datetime.now(),
                    'sale_order_line_id': sale_line.id,
                    'sale_price': line.unit_price,
                    'last_status_change_date': fields.Datetime.now(),
                    'last_status_change_user_id': self.env.user.id,
                })
                
                _logger.info(f"Detalle de seguimiento marcado como vendido para producto {line.product_id.name}")
                
                # Recargar el registro para verificar
                tracking_detail = self.env['loan.tracking.detail'].browse(tracking_detail.id)
                if tracking_detail.status != 'sold':
                    raise UserError(_(
                        f"Error al actualizar el estado del producto {line.product_id.name} a 'vendido'. "
                        f"Estado actual: {tracking_detail.status}"
                    ))
                    
                # Registrar mensaje en el chatter
                tracking_detail.message_post(
                    body=_(
                        f"Producto convertido a venta\n"
                        f"- Precio de venta: {line.unit_price}\n"
                        f"- Orden de venta: {sale_line.order_id.name}\n"
                        f"- Línea: {sale_line.name}"
                    ),
                    message_type='comment'
                )
                
                # Forzar recálculo de cantidades
                product = line.product_id
                loans_qty = product._get_active_loans_qty()
                available_real = product.qty_available - loans_qty
                
                product.invalidate_recordset(['qty_in_loans', 'qty_available_real'])
                product.write({
                    'qty_in_loans': loans_qty,
                    'qty_available_real': available_real
                })
                
                _logger.info(
                    f"Actualizadas cantidades para {product.name}: "
                    f"En préstamo={loans_qty}, "
                    f"Disponible={available_real}"
                )
                
            except Exception as e:
                _logger.error(f"Error al marcar como vendido el producto {line.product_id.name}: {str(e)}")
                raise UserError(_(
                    f"Error al procesar la venta del producto {line.product_id.name}: {str(e)}"
                ))
        
        return sale_order

    def _create_sale_order(self, sale_lines):
        """Crear orden de venta para productos comprados"""
        order_lines = []
        
        # Agrupar líneas por producto si no tienen números de serie específicos
        grouped_lines = {}
        for line in sale_lines:
            key = (line.product_id.id, line.unit_price)
            if line.product_id.tracking == 'serial':
                # Para productos con serie, una línea por cada número de serie
                key = (line.product_id.id, line.unit_price, line.lot_id.id if line.lot_id else 0)
            
            if key not in grouped_lines:
                grouped_lines[key] = {
                    'product_id': line.product_id.id,
                    'quantity': 0,
                    'price': line.unit_price,
                    'lot_name': line.lot_id.name if line.lot_id else None
                }
            
            grouped_lines[key]['quantity'] += line.qty_to_resolve
        
        # Crear líneas de orden de venta
        for group_data in grouped_lines.values():
            line_name = group_data['lot_name']
            if line_name:
                line_name = f"Conversión préstamo - S/N: {line_name}"
            else:
                line_name = "Conversión de préstamo"
            
            order_lines.append((0, 0, {
                'product_id': group_data['product_id'],
                'product_uom_qty': group_data['quantity'],
                'price_unit': group_data['price'],
                'name': line_name,
            }))
        
        # Crear la orden de venta
        sale_vals = {
            'partner_id': self.partner_id.id,
            'origin': f"Conversión préstamo {self.picking_id.name}",
            'note': f"Orden creada desde resolución de préstamo. Notas: {self.notes or 'N/A'}",
            'order_line': order_lines,
            'date_order': self.resolution_date,
        }
        
        sale_order = self.env['sale.order'].create(sale_vals)
        
        # Vincular con el préstamo original
        self.picking_id.conversion_sale_order_id = sale_order.id
        
        return sale_order

    def _process_returns(self):
        """Procesar productos que el cliente devuelve"""
        return_lines = self.resolution_line_ids.filtered(
            lambda l: l.resolution_type == 'return'
        )
        
        if not return_lines:
            return None
        
        # Crear picking de devolución
        return_picking = self._create_return_picking(return_lines)
        
        # Actualizar detalles de seguimiento según la condición seleccionada
        for line in return_lines:
            # Mapear condición a estado final
            condition_to_status = {
                'good': 'returned_good',
                'damaged': 'returned_damaged', 
                'defective': 'returned_defective'
            }
            
            final_status = condition_to_status.get(line.return_condition, 'returned_good')
            
            line.tracking_detail_id.write({
                'status': final_status,
                'resolution_date': fields.Datetime.now(),
                'return_picking_id': return_picking.id,
                'return_condition_notes': f"Devuelto el {fields.Date.today()} en condición: {dict(line._fields['return_condition'].selection)[line.return_condition]}",
                'notes': f"Marcado para devolución el {fields.Date.today()}. Condición: {line.return_condition}"
            })
        
        return return_picking

    def _create_return_picking(self, return_lines):
        """Crear picking de devolución SIN validación de stock"""
        # Determinar ubicación de destino
        main_warehouse = self.env['stock.warehouse'].search([
            ('warehouse_type', '!=', 'loans')
        ], limit=1)
        
        if not main_warehouse:
            raise UserError(_("No se encontró almacén principal para devoluciones."))
        
        # Determinar tipo de operación de devolución
        return_type = self.picking_id.picking_type_id  # Usar el mismo tipo por defecto
        
        # Crear picking de devolución
        picking_vals = {
            'partner_id': self.partner_id.id,
            'picking_type_id': return_type.id,
            'location_id': self.picking_id.location_dest_id.id,  # Desde ubicación de préstamo
            'location_dest_id': main_warehouse.lot_stock_id.id,  # A almacén principal
            'origin': f"Resolución Devolución {self.picking_id.name}",  # CAMBIO: indicar que es devolución
            'note': f"Devolución procesada desde resolución de préstamo. Notas: {self.notes or 'N/A'}",
            'scheduled_date': self.resolution_date,
            'is_loan': False,  # CAMBIO: marcar como NO préstamo para evitar validaciones
            'loaned_to_partner_id': self.partner_id.id,  # AGREGAR: asignar cliente para evitar error de validación
            'loan_return_origin_id': self.picking_id.id,  # CAMBIO: marcar origen
            'move_ids_without_package': []
        }
        
        # Crear movimientos
        moves = []
        for line in return_lines:
            move_vals = {
                'product_id': line.product_id.id,
                'product_uom_qty': line.qty_to_resolve,
                'product_uom': line.product_id.uom_id.id,
                'location_id': self.picking_id.location_dest_id.id,
                'location_dest_id': main_warehouse.lot_stock_id.id,
                'name': f"Devolución: {line.product_id.name}",
                'origin': f"Resolución Devolución {self.picking_id.name}",  # CAMBIO
                'state': 'draft',
            }
            
            # Para productos con número de serie, especificar el lote
            if line.lot_id:
                move_vals['lot_ids'] = [(4, line.lot_id.id)]
            
            moves.append((0, 0, move_vals))
        
        picking_vals['move_ids_without_package'] = moves
        return_picking = self.env['stock.picking'].create(picking_vals)
        
        # Confirmar automáticamente el picking (ahora sin validación de stock)
        return_picking.action_confirm()
        
        return return_picking

    def _process_continued_loans(self):
        """Procesar productos que siguen en préstamo"""
        continued_lines = self.resolution_line_ids.filtered(
            lambda l: l.resolution_type == 'keep_loan'
        )
        
        continued_details = []
        
        for line in continued_lines:
            # Mantener el detalle de seguimiento como activo
            line.tracking_detail_id.write({
                'notes': f"Préstamo extendido el {fields.Date.today()}. Resolución: mantener en préstamo."
            })
            continued_details.append(line.tracking_detail_id)
        
        return continued_details

    def _update_original_loan_state(self):
        """Actualizar el estado del préstamo original basado en la resolución"""
        # Determinar nuevo estado basado en qué quedó pendiente
        if self.has_continued_loans:
            new_state = 'partially_resolved'
        else:
            new_state = 'completed'
        
        self.picking_id.write({
            'loan_state': new_state,
            'loan_notes': (self.picking_id.loan_notes or '') + f"\n\nResolución {fields.Date.today()}: {self.notes or 'Procesado'}"
        })

    def _return_resolution_results(self, results):
        """Retornar vista con resultados de la resolución"""
        message_parts = ["Resolución de préstamo procesada exitosamente:"]
        
        if results['sale_order']:
            message_parts.append(f"• Orden de venta creada: {results['sale_order'].name}")
        
        if results['return_picking']:
            message_parts.append(f"• Devolución creada: {results['return_picking'].name}")
        
        if results['continued_details']:
            count = len(results['continued_details'])
            message_parts.append(f"• {count} item(s) continúan en préstamo")
        
        # Crear mensaje usando el sistema de mensajes
        message = "\n".join(message_parts)
        
        # Mostrar mensaje en la interfaz
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Resolución Completada',
                'message': message,
                'type': 'success',
                'sticky': True,
                'next': {
                    'type': 'ir.actions.act_window',
                    'res_model': 'stock.picking',
                    'res_id': self.picking_id.id,
                    'view_mode': 'form',
                    'views': [(False, 'form')],
                    'target': 'current',
                }
            }
        }
    
    def _find_or_create_tracking_detail(self, line):
        """Buscar o crear tracking detail para una línea específica"""
        # Primero intentar encontrar un tracking detail existente
        existing_detail = self.env['loan.tracking.detail'].search([
            ('picking_id', '=', self.picking_id.id),
            ('product_id', '=', line.product_id.id),
            ('status', 'in', ['active', 'pending_resolution'])
        ], limit=1)
        
        if existing_detail:
            return existing_detail
        
        # Si no existe, crear uno nuevo basado en los movimientos del picking
        for move in self.picking_id.move_ids_without_package:
            if move.product_id.id == line.product_id.id and move.state == 'done':
                
                if move.product_id.tracking == 'serial':
                    # Para productos con serie, crear uno por cada move_line
                    for move_line in move.move_line_ids:
                        if move_line.lot_id and move_line.qty_done > 0:
                            # Verificar si ya existe para este lote
                            lot_detail = self.env['loan.tracking.detail'].search([
                                ('picking_id', '=', self.picking_id.id),
                                ('product_id', '=', move.product_id.id),
                                ('lot_id', '=', move_line.lot_id.id)
                            ], limit=1)
                            
                            if not lot_detail:
                                lot_detail = self.env['loan.tracking.detail'].create({
                                    'picking_id': self.picking_id.id,
                                    'product_id': move.product_id.id,
                                    'lot_id': move_line.lot_id.id,
                                    'quantity': move_line.qty_done,
                                    'status': 'active',
                                    'loan_date': self.picking_id.date_done or fields.Datetime.now(),
                                    'original_cost': move.product_id.standard_price,
                                })
                            
                            if lot_detail.product_id.id == line.product_id.id:
                                return lot_detail
                else:
                    # Para productos sin serie
                    qty_done = sum(move.move_line_ids.mapped('qty_done'))
                    if qty_done > 0:
                        detail = self.env['loan.tracking.detail'].create({
                            'picking_id': self.picking_id.id,
                            'product_id': move.product_id.id,
                            'quantity': qty_done,
                            'status': 'active',
                            'loan_date': self.picking_id.date_done or fields.Datetime.now(),
                            'original_cost': move.product_id.standard_price,
                        })
                        return detail
        
        return None
    def action_process_resolution(self):
        """Acción llamada desde el botón de la vista para procesar la resolución"""
        self.ensure_one()
        try:
            result = self._process_resolution()
            return result
        except Exception as e:
            raise UserError(_(
                f"Error al procesar la resolución del préstamo:\n{str(e)}"
            ))


class LoanResolutionWizardLine(models.TransientModel):
    _name = 'loan.resolution.wizard.line'
    _description = 'Línea de Resolución de Préstamo'

    wizard_id = fields.Many2one(
        'loan.resolution.wizard',
        required=True,
        ondelete='cascade'
    )
    
    tracking_detail_id = fields.Many2one(
        'loan.tracking.detail',
        string='Detalle de Seguimiento',
        required=True,
        ondelete='cascade'
    )
    
    product_id = fields.Many2one(
        'product.product',
        string='Producto',
        required=True,  
        readonly=True   # Agregar readonly para evitar modificaciones
    )
    
    lot_id = fields.Many2one(
        'stock.lot',
        string='Número de Serie/Lote'
    )
    
    loaned_qty = fields.Float(
        string='Cantidad Prestada',
        digits='Product Unit of Measure'
    )
    
    qty_to_resolve = fields.Float(
        string='Cantidad a Resolver',
        required=True,
        digits='Product Unit of Measure',
        help="Cantidad que se resolverá con la decisión seleccionada"
    )
    
    resolution_type = fields.Selection([
        ('buy', 'Comprar'),
        ('return', 'Devolver'),
        ('keep_loan', 'Mantener Préstamo')
    ], string='Decisión', required=True, default='keep_loan')
    
    # Campos para venta
    unit_price = fields.Float(
        string='Precio Unitario',
        digits='Product Price',
        help="Precio por unidad si se decide comprar"
    )
    
    total_price = fields.Float(
        string='Total',
        compute='_compute_total_price',
        digits='Product Price'
    )
    
    # Campos para devolución
    return_condition = fields.Selection([
        ('good', 'Buen Estado'),
        ('damaged', 'Dañado'),
        ('defective', 'Defectuoso')
    ], string='Condición', default='good')
    
    notes = fields.Text(
        string='Observaciones',
        help="Notas específicas para este item"
    )

    @api.depends('qty_to_resolve', 'unit_price')
    def _compute_total_price(self):
        """Calcular precio total"""
        for line in self:
            line.total_price = line.qty_to_resolve * line.unit_price

    @api.onchange('product_id')
    def _onchange_product_id(self):
        """Auto-llenar precio basado en lista de precios del producto"""
        if self.product_id:
            self.unit_price = self.product_id.list_price

    @api.onchange('resolution_type')
    def _onchange_resolution_type(self):
        """Manejar cambios en el tipo de resolución"""
        if self.resolution_type == 'buy':
            # Auto-llenar precio si no está establecido
            if not self.unit_price and self.product_id:
                self.unit_price = self.product_id.list_price
        elif self.resolution_type in ('return', 'keep_loan'):
            # Limpiar campos de precio
            self.unit_price = 0.0

    @api.constrains('qty_to_resolve', 'loaned_qty', 'tracking_detail_id')
    def _check_quantity_consistency(self):
        """Validar consistencia de cantidades"""
        for line in self:
            if not line.tracking_detail_id:
                continue
            
            tracking_qty = line.tracking_detail_id.quantity
            if line.qty_to_resolve > tracking_qty:
                raise ValidationError(_(
                    f"Error de cantidad para {line.product_id.name}:\n"
                    f"- Cantidad prestada registrada: {tracking_qty}\n"
                    f"- Cantidad a resolver: {line.qty_to_resolve}\n"
                    f"La cantidad a resolver no puede ser mayor a la prestada."
                ))
            
            if line.qty_to_resolve <= 0:
                raise ValidationError(_(
                    f"La cantidad a resolver debe ser mayor a 0 para {line.product_id.name}"
                ))
            
            # Para productos con número de serie, solo se permiten cantidades enteras de 1
            if (line.product_id.tracking == 'serial' and 
                line.qty_to_resolve != 1):
                raise ValidationError(_(
                    f"Los productos con número de serie solo permiten cantidades de 1. "
                    f"Producto: {line.product_id.name}"
                ))

    @api.constrains('unit_price', 'resolution_type')
    def _check_sale_price(self):
        """Validar precio de venta"""
        for line in self:
            if line.resolution_type == 'buy' and line.unit_price <= 0:
                raise ValidationError(_(
                    f"El precio de venta debe ser mayor a 0 para {line.product_id.name}"
                ))
            
    @api.constrains('tracking_detail_id')
    def _check_tracking_detail_validity(self):
        """Validar que el tracking detail sea válido y corresponda al wizard"""
        for line in self:
            if line.tracking_detail_id:
                # Verificar que el tracking detail existe
                if not line.tracking_detail_id.exists():
                    raise ValidationError(_(
                        f"El detalle de seguimiento para {line.product_id.name} no es válido."
                    ))
                
                # Verificar que pertenece al mismo picking
                if line.wizard_id.picking_id and line.tracking_detail_id.picking_id != line.wizard_id.picking_id:
                    raise ValidationError(_(
                        f"El detalle de seguimiento para {line.product_id.name} no corresponde al préstamo seleccionado."
                    ))
                
                # Verificar que el estado permite resolución
                if line.tracking_detail_id.status not in ['active', 'pending_resolution']:
                    raise ValidationError(_(
                        f"El producto {line.product_id.name} ya fue resuelto (estado: {line.tracking_detail_id.status}). "
                        "No se puede resolver nuevamente."
                    ))