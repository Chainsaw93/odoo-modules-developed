from odoo import models

class SaleOrder(models.Model):
    _inherit = 'sale.order'
    
    def _create_invoices(self, grouped=False, final=False, date=None):
        """Agregar contexto para permitir conversión de orden a factura"""
        # Agregar contexto más robusto que indique que estamos creando desde orden de venta
        context = {
            'creating_from_sale_order': True,
            'skip_draft_invoice_validation': True,
            'default_move_type': 'out_invoice',
            'active_model': 'sale.order',
            'active_ids': self.ids,
            'active_id': self.id if len(self) == 1 else False,
        }
        
        return super(SaleOrder, self.with_context(**context))._create_invoices(
            grouped=grouped, 
            final=final, 
            date=date
        )
    
    def action_create_invoice(self):
        """Sobrescribir para mantener el contexto en creación manual de facturas"""
        context = {
            'creating_from_sale_order': True,
            'skip_draft_invoice_validation': True,
            'default_move_type': 'out_invoice',
            'active_model': 'sale.order',
            'active_ids': self.ids,
            'active_id': self.id if len(self) == 1 else False,
        }
        
        return super(SaleOrder, self.with_context(**context)).action_create_invoice()
    
    def _prepare_invoice(self):
        """Sobrescribir para asegurar que el contexto se mantenga en la preparación de datos"""
        invoice_vals = super()._prepare_invoice()
        
        # Asegurar que los valores de la factura incluyan información del origen
        if not invoice_vals.get('invoice_origin'):
            invoice_vals['invoice_origin'] = self.name
            
        return invoice_vals