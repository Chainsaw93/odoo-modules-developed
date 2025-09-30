from odoo import models, fields

class AccountAsset(models.Model):
    _inherit = 'account.asset'

    prestamo = fields.Boolean(string="Préstamo", default=False)
    responsable = fields.Char(string="Responsable")
    ubicacion = fields.Char(string="Ubicación")

    