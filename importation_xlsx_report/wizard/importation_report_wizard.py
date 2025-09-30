from odoo import models, fields, api
from odoo.exceptions import UserError

class ImportationReportWizard(models.TransientModel):
    _name = 'importation.report.wizard'
    _description = 'Wizard para generar reporte de importación'

    importation_id = fields.Many2one('trade.importation', string='Importación', required=True)
    
    def action_generate_report(self):
        """Genera el reporte Excel"""
        if not self.importation_id:
            raise UserError("Debe seleccionar una importación.")
        
        return self.importation_id.generate_importation_excel_report()