from odoo import models, fields, api
from odoo.exceptions import ValidationError

class AccountAsset(models.Model):
    _inherit = 'account.asset'

    responsible_id = fields.Many2one('hr.employee', string="Responsable Actual")
    delivery_date = fields.Date(string="Fecha de Entrega")
    delivery_state = fields.Selection([
        ('nuevo', 'Nuevo'),
        ('usado', 'Usado'),
        ('daniado', 'Dañado')
    ], string="Estado al Entregar")

    return_date = fields.Date(string="Fecha de Devolución")
    return_state = fields.Selection([
        ('bueno', 'Bueno'),
        ('daniado', 'Dañado'),
        ('irreparable', 'Irreparable')
    ], string="Estado al Devolver")

    responsible_history_ids = fields.One2many(
        'asset.responsible.history', 'asset_id', string="Historial de Responsables", readonly=True
    )

    def action_deliver_asset(self):
        """Acción para entregar un activo a un responsable"""
        for asset in self:
            if not asset.responsible_id or not asset.delivery_date or not asset.delivery_state:
                raise ValidationError("Debe completar Responsable, Fecha de Entrega y Estado.")
            # Aquí puedes agregar lógica adicional si es necesario

    def action_return_asset(self):
        """Acción para devolver un activo y crear el registro histórico"""
        for asset in self:
            if not asset.return_date or not asset.return_state:
                raise ValidationError("Debe completar la Fecha de Devolución y Estado.")
            
            # Crear registro en el historial
            self.env['asset.responsible.history'].create({
                'asset_id': asset.id,
                'responsible_id': asset.responsible_id.id if asset.responsible_id else False,
                'delivery_date': asset.delivery_date,
                'delivery_state': asset.delivery_state,
                'return_date': asset.return_date,
                'return_state': asset.return_state,
            })
            
            # Limpiar campos actuales
            asset.write({
                'responsible_id': False,
                'delivery_date': False,
                'delivery_state': False,
                'return_date': False,
                'return_state': False,
            })


class AssetResponsibleHistory(models.Model):
    _name = 'asset.responsible.history'
    _description = 'Historial de Responsables de Activos'
    _order = 'delivery_date desc'
    _rec_name = 'responsible_id'

    asset_id = fields.Many2one('account.asset', string="Activo", required=True, ondelete='cascade')
    responsible_id = fields.Many2one('hr.employee', string="Responsable")
    delivery_date = fields.Date(string="Fecha de Entrega")
    delivery_state = fields.Selection([
        ('nuevo', 'Nuevo'),
        ('usado', 'Usado'),
        ('daniado', 'Dañado')
    ], string="Estado al Entregar")

    return_date = fields.Date(string="Fecha de Devolución")
    return_state = fields.Selection([
        ('bueno', 'Bueno'),
        ('daniado', 'Dañado'),
        ('irreparable', 'Irreparable')
    ], string="Estado al Devolver")

    @api.constrains('delivery_date', 'return_date')
    def _check_dates(self):
        """Validar que la fecha de devolución sea posterior a la de entrega"""
        for record in self:
            if record.delivery_date and record.return_date:
                if record.return_date < record.delivery_date:
                    raise ValidationError("La fecha de devolución no puede ser anterior a la fecha de entrega.")