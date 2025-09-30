from odoo import fields, models, api

class ResUsers(models.Model):
    _inherit = 'res.users'

    allow_modify_draft_invoice = fields.Boolean(
        string="Permitir modificar facturas en borrador",
        compute="_compute_allow_modify_draft_invoice",
        inverse="_inverse_allow_modify_draft_invoice",
        help="Al activarlo, el usuario obtiene/quita el grupo que le permite editar facturas en estado borrador."
    )

    @api.depends('groups_id')
    def _compute_allow_modify_draft_invoice(self):
        group = self.env.ref('bloqueo_factura_ventas_borrador.group_modify_draft_invoice', raise_if_not_found=False)
        for user in self:
            user.allow_modify_draft_invoice = bool(group and group in user.groups_id)

    def _inverse_allow_modify_draft_invoice(self):
        group = self.env.ref('bloqueo_factura_ventas_borrador.group_modify_draft_invoice', raise_if_not_found=False)
        if not group:
            return
        for user in self:
            if user.allow_modify_draft_invoice:
                user.groups_id |= group
            else:
                user.groups_id -= group