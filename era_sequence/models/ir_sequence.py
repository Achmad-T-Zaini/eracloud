from datetime import datetime, timedelta
import logging
import pytz

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

from odoo import tools
from collections import OrderedDict

class ir_sequence(models.Model):
    _inherit = 'ir.sequence'

    def write_sms_ou(self):
        return 'OU'

    def write_roman(self,num):

        roman = OrderedDict()
        roman[1000] = "M"
        roman[900] = "CM"
        roman[500] = "D"
        roman[400] = "CD"
        roman[100] = "C"
        roman[90] = "XC"
        roman[50] = "L"
        roman[40] = "XL"
        roman[10] = "X"
        roman[9] = "IX"
        roman[5] = "V"
        roman[4] = "IV"
        roman[1] = "I"

        def roman_num(num):
            for r in roman.keys():
                x, y = divmod(num, r)
                yield roman[r] * x
                num -= (r * x)
                if num > 0:
                    roman_num(num)
                else:
                    break

        return "".join([a for a in roman_num(num)])
    
    def _get_prefix_suffix(self, date=None, date_range=None):
        def _interpolate(s, d):
            return (s % d) if s else ''

        def _interpolation_dict():
            now = range_date = effective_date = datetime.now(pytz.timezone(self._context.get('tz') or 'UTC'))
            if date or self._context.get('ir_sequence_date'):
                effective_date = fields.Datetime.from_string(date or self._context.get('ir_sequence_date'))
            if date_range or self._context.get('ir_sequence_date_range'):
                range_date = fields.Datetime.from_string(date_range or self._context.get('ir_sequence_date_range'))

            sequences = {
                'year': '%Y', 'month': '%m', 'day': '%d', 'y': '%y', 'doy': '%j', 'woy': '%W',
                'weekday': '%w', 'h24': '%H', 'h12': '%I', 'min': '%M', 'sec': '%S',
                #Additional dict for roman
                'rom_year': '%Y', 'rom_month': '%m', 'rom_y': '%y', 'rom_day': '%d',
                #Additional dict for PSI Sequence
                'era_code': '%Y'
            }
            res = {}
            for key, format in sequences.items():
                if "rom_" in key:  
                    #Convert to Roman
                    res[key] = self.write_roman(int(effective_date.strftime(format)))
                    res['range_' + key] = self.write_roman(int(range_date.strftime(format)))
                    res['current_' + key] = self.write_roman(int(now.strftime(format)))
                elif "era_code" in key:
                    res[key] = self.write_sms_ou()
                else:
                    res[key] = effective_date.strftime(format)
                    res['range_' + key] = range_date.strftime(format)
                    res['current_' + key] = now.strftime(format)
            # print(res)
            # raise EnvironmentError
            return res

        self.ensure_one()
        d = _interpolation_dict()
        try:
            interpolated_prefix = _interpolate(self.prefix, d)
            interpolated_suffix = _interpolate(self.suffix, d)
        except ValueError:
            raise UserError(_('Invalid prefix or suffix for sequence \'%s\'') % self.name)
        return interpolated_prefix, interpolated_suffix

    @api.model
    def next_by_code_era(self, sequence_code, sequence_era_code, sequence_date=None):
        """ Draw an interpolated string using a sequence with the requested code.
            If several sequences with the correct code are available to the user
            (multi-company cases), the one from the user's current company will
            be used.
        """
        self.check_access_rights('read')
        company_id = self.env.company.id
        seq_ids = self.search([('code', '=', sequence_code), ('company_id', 'in', [company_id, False])], order='company_id')
        if not seq_ids:
            _logger.debug("No ir.sequence has been found for code '%s'. Please make sure a sequence is set for current company." % sequence_code)
            return False
        seq_id = seq_ids[0]
        new_seq = seq_id._next(sequence_date=sequence_date)
        new_seq = new_seq.replace("OU", str(sequence_era_code))
        return new_seq

    @api.model
    def next_by_id_era(self, sequence_id, sequence_era_code, sequence_date=None):
        """ Draw an interpolated string using a sequence with the requested code.
            If several sequences with the correct code are available to the user
            (multi-company cases), the one from the user's current company will
            be used.
        """
        self.check_access_rights('read')
        company_id = self.env.company.id
        seq_id = sequence_id
        new_seq = seq_id._next(sequence_date=sequence_date)
        new_seq = new_seq.replace("OU", str(sequence_era_code))
        return new_seq
