from wtforms import Form, Field, StringField, IntegerField, validators
from wtforms.utils import unset_value
from Metadata import default_required_metadata, validate_metadata

class MetadataField(Field):
    required_metadata = default_required_metadata
    allowed_dtypes = ('str', 'int', 'float', 'bool')

    def getfieldname(self, basename, index):
        """ Get the full name for a field with entry could `index` """
        return f"{self.name}_{basename}_{index}"
    
    def process(self, formdata, data=unset_value):
        super().process(None, data)
        if formdata is None or len(formdata) == 0:
            return self.data
        
        result = dict()
        comments = result.setdefault('comments',dict())
        index = 0
        while True:
            key = formdata.get(self.getfieldname('key',index))
            if not key:
                break
            val = formdata.get(self.getfieldname('value', index))
            dtype = formdata.get(self.getfieldname('dtype', index), 'str')
            try:
                if dtype == 'bool':
                    if val in ('1','T','yes','on','true','True'):
                        val = True
                    elif val in ('0','F','no','off','false','False'):
                        val = False
                    else:
                        raise ValueError(f"Can't parse {val} as type bool")
                elif dtype == 'int':
                    val = int(val)
                elif dtype == 'float':
                    val = float(val)
            except ValueError as e:
                self.process_errors.append(key+": "+e.args[0])
                    
            result[key] = val
            comment = formdata.get(self.getfieldname('comment', index))
            if comment:
                comments[key] = comment
            index += 1

        try: 
            valid = validate_metadata(result, self.required_metadata)
            if not valid:
                raise ValueError("Validation failed")
        except ValueError as e:
            self.process_errors.append(e.args[0])

        self.data = result
        return self.data


class ExposeForm(Form):
    exposure = IntegerField("Exposure (s)", [validators.required(),
                                             validators.NumberRange(0)],
                            default=5)
    nexposures = IntegerField("Number of exposures",
                              [validators.required(), 
                               validators.NumberRange(0)],
                              default=1)
    filename = StringField("Filename", [validators.required()],
                           default="Image", render_kw={'readonly': 'readonly'})
    metadata = MetadataField("Metadata")
    
