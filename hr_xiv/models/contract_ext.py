from odoo import fields, models, api
from odoo.exceptions import UserError


class HrContract(models.Model):
    _inherit = 'hr.contract'
    _description = 'Extend Contract Form for XIV'

    # Fields
    accumulate_xiv = fields.Boolean(
        'Accumulate XIV',
        help="Enable XIV salary accumulation for this contract"
    )
    accumulated_xiv_amount = fields.Float(
        'XIV Accumulated',
        help='XIV amount accumulated since hiring or from period start to date.\n'
             'Edit manually only to set initial values.'
    )
    sbu_amount = fields.Float(
        'SBU Amount',
        help='Unified Basic Salary amount for XIV calculation.\n'
             'If not set, system will use company parameter or default value.',
        default=lambda self: self._get_default_sbu()
    )

    def _get_default_sbu(self):
        """Get default SBU value from system parameter or fallback"""
        return float(self.env['ir.config_parameter'].sudo().get_param(
            'hr_xiv.default_sbu_amount', '460.00'  # Ecuador 2024 SBU as fallback
        ))

    def get_monthly_xiv_amount(self):
        """Calculate monthly XIV amount based on SBU"""
        self.ensure_one()
        
        sbu_value = self._get_current_sbu_value()
        monthly_xiv = round(float(sbu_value / 360) * 30, 2) if sbu_value else 0.0
        return monthly_xiv

    def get_current_sbu(self):
        """Get current SBU (Salario Básico Unificado) value"""
        self.ensure_one()
        return self._get_current_sbu_value()

    def _get_current_sbu_value(self):
        """Get SBU value from contract, system parameter, or fallback"""
        # 1. Try contract-specific SBU
        if self.sbu_amount:
            return self.sbu_amount
            
        # 2. Try system parameter
        sbu_param = self.env['ir.config_parameter'].sudo().get_param(
            'hr_xiv.default_sbu_amount'
        )
        if sbu_param:
            try:
                return float(sbu_param)
            except ValueError:
                pass
                
        # 3. Fallback to Ecuador 2024 SBU
        return 460.00

    def get_accumulated_xiv_amount(self):
        """Calculate accumulated XIV amount based on tenure and SBU"""
        self.ensure_one()
        
        if not self.date_start:
            return self.accumulated_xiv_amount or 0.0
            
        today = fields.Date.today()
        months_worked = self._calculate_months_worked(today)
        
        if months_worked >= 11:
            # Employee has worked 11+ months, gets full SBU
            return self._get_current_sbu_value()
        else:
            # Employee hasn't completed minimum period, use accumulated amount
            return self.accumulated_xiv_amount or 0.0

    def _calculate_months_worked(self, reference_date):
        """Calculate number of months worked from contract start to reference date"""
        self.ensure_one()
        
        if not self.date_start:
            return 0
            
        months_worked = (
            (reference_date.year - self.date_start.year) * 12 + 
            (reference_date.month - self.date_start.month)
        )
        return max(0, months_worked)

    def get_xiv_period(self):
        """Get XIV calculation period from configuration"""
        self.ensure_one()
        
        # Get regime from contract (field should come from hr_job_regime_base)
        regime = getattr(self, 'regime', None)
        if not regime:
            raise UserError(
                'Please configure regime in contract.\n'
                'This field should be provided by hr_job_regime_base module.'
            )
            
        xiv_config = self.env['hr.xiv.config'].search([('regime', '=', regime)], limit=1)
        if not xiv_config:
            raise UserError(
                f'Please configure XIV period for regime "{regime}" in Payroll Application.\n'
                'Go to Payroll > Configuration > XIV Configuration'
            )
        return xiv_config.init_date_xiv, xiv_config.end_date_xiv

    def get_xiv_pay_date(self):
        """Get XIV payment date from configuration"""
        self.ensure_one()
        
        # Get regime from contract (field should come from hr_job_regime_base)
        regime = getattr(self, 'regime', None)
        if not regime:
            raise UserError(
                'Please configure regime in contract.\n'
                'This field should be provided by hr_job_regime_base module.'
            )
            
        xiv_config = self.env['hr.xiv.config'].search([('regime', '=', regime)], limit=1)
        if not xiv_config:
            raise UserError(
                f'Please configure XIV period for regime "{regime}" in Payroll Application.\n'
                'Go to Payroll > Configuration > XIV Configuration'
            )
        return xiv_config.pay_date_xiv

    # Legacy method names for backwards compatibility
    @api.model
    def month_xiv_amount(self):
        """Legacy method - use get_monthly_xiv_amount() instead"""
        return self.get_monthly_xiv_amount()

    @api.model  
    def acc_xiv_amount(self):
        """Legacy method - use get_accumulated_xiv_amount() instead"""
        return self.get_accumulated_xiv_amount()