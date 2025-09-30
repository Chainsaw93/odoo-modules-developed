from odoo import fields, models, api
import datetime
from odoo.exceptions import UserError


class HrContract(models.Model):
    _inherit = 'hr.contract'
    _description = 'Extend Contract Form for XIII'

    # Fields
    accumulate_xiii = fields.Boolean(
        'Accumulate XIII',
        help="Enable XIII salary accumulation for this contract"
    )
    is_monthly_xiii = fields.Boolean(
        'XIII by Month', 
        default=True,
        help="Calculate XIII salary on a monthly basis"
    )
    monthly_xiii_amount = fields.Float(
        'XIII Month', 
        compute='_compute_xiii',
        help="Monthly XIII amount based on accumulated salary"
    )
    accumulated_xiii_amount = fields.Float(
        'XIII Accumulated', 
        compute='_compute_xiii',
        help="Total accumulated XIII amount for the period"
    )

    @api.depends('employee_id.payslip_count')
    def _compute_xiii(self):
        """Compute XIII amounts based on payslips in the period"""
        for record in self:
            if not record.employee_id:
                record.accumulated_xiii_amount = 0.0
                record.monthly_xiii_amount = 0.0
                continue
                
            try:
                init_date, end_date = record.get_xiii_period()
                payslips = self.env['hr.payslip'].search([
                    ('employee_id', '=', record.employee_id.id), 
                    ('date_from', '>=', init_date), 
                    ('date_from', '<=', end_date),
                    ('state', '=', 'done')
                ])
                
                total_basic = 0.0
                for payslip in payslips:
                    for line in payslip.line_ids:
                        if line.code == 'BASIC':
                            total_basic += line.amount
                
                record.accumulated_xiii_amount = total_basic
                # TODO: Check if employee has worked more than one year or consider months since hiring
                record.monthly_xiii_amount = round(total_basic / 12, 2) if total_basic else 0.0
                
            except UserError:
                record.accumulated_xiii_amount = 0.0
                record.monthly_xiii_amount = 0.0

    def accumulated_xiii_amount_by_employee(self, employee_id):
        """Calculate accumulated XIII amount for specific employee"""
        self.ensure_one()
        
        try:
            from_date, to_date = self.get_xiii_period()
        except UserError:
            return 0.0
            
        year = fields.Date.today().year
        worker_months = self._calculate_worker_months(year)
        
        if worker_months <= 0:
            return 0.0

        # Optimized SQL query for Odoo 18
        query = """
            SELECT SUM(
                CASE WHEN hp.credit_note IS NOT TRUE 
                THEN pl.total 
                ELSE -pl.total 
                END
            )
            FROM hr_payslip hp
            INNER JOIN hr_payslip_line pl ON hp.id = pl.slip_id
            INNER JOIN hr_salary_rule_category rc ON rc.id = pl.category_id
            WHERE hp.employee_id = %s 
                AND hp.state = 'done'
                AND hp.date_from >= %s 
                AND hp.date_to <= %s 
                AND rc.code = 'BASIC'
        """
        
        self.env.cr.execute(query, (employee_id, from_date, to_date))
        result = self.env.cr.fetchone()
        
        total_amount = result[0] if result and result[0] else 0.0
        amount_xiii = round(total_amount / worker_months, 2) if total_amount and worker_months > 0 else 0.0
        
        return amount_xiii

    def month_xiii_amount_by_employee(self, employee_id):
        """Calculate monthly XIII amount for specific employee"""
        # This method has the same logic as accumulated_xiii_amount_by_employee
        # Keeping separate for backwards compatibility
        return self.accumulated_xiii_amount_by_employee(employee_id)

    def _calculate_worker_months(self, year):
        """Calculate number of months the employee has worked in the given year"""
        self.ensure_one()
        
        if not self.date_start:
            return 0
            
        today = fields.Date.today()
        year_start = datetime.date(year, 1, 1)
        
        if self.date_start < year_start:
            # Employee started before current year
            worker_months = today.month
        else:
            # Employee started during current year
            worker_months = today.month - self.date_start.month + 1
            
        return max(0, worker_months)

    def get_xiii_period(self):
        """Get XIII calculation period from company configuration"""
        self.ensure_one()
        
        company = self.company_id or self.env.company
        
        if not company.xiii_init_date or not company.xiii_end_date:
            raise UserError(
                'Please configure XIII period in Payroll Settings.\n'
                'Go to Settings > Payroll > XIII Salary Configuration'
            )
        return company.xiii_init_date, company.xiii_end_date

    def get_xiii_pay_date(self):
        """Get XIII payment date from company configuration"""
        self.ensure_one()
        
        company = self.company_id or self.env.company
        
        if not company.xiii_pay_date:
            raise UserError(
                'Please configure XIII payment date in Payroll Settings.\n'
                'Go to Settings > Payroll > XIII Salary Configuration'
            )
        return company.xiii_pay_date