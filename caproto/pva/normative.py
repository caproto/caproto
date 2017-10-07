# TODO: class-based definitions + usual introspection abilities as well?
# TODO: NTValue class which helps handle a structured value of an NTType?

import copy
import logging

from . import introspection as intro
from . import types
from .helpers import (FieldDescHelper, StructuredValueBase)


logger = logging.getLogger(__name__)

basic_type_definitions = (
    '''
    struct time_t
        long secondsPastEpoch
        int nanoseconds
        int userTag
    ''',

    '''
    struct alarm_t
        int severity
        int status
        string message
    ''',

    '''
    struct time_t
        long secondsPastEpoch
        int nanoseconds
        int userTag
    ''',

    '''
    struct display_t
        double limitLow
        double limitHigh
        string description
        string format
        string units
    ''',

    '''
    struct control_t
        double limitLow
        double limitHigh
        double minStep
    '''

)


class NormativeTypeBase(FieldDescHelper):
    def __init__(self, definition, *, user_types=None,
                 value_class=StructuredValueBase):
        if user_types is None:
            user_types = basic_types

        type_string = 'struct {}'.format(self.type_name)
        self.definition = [(type_string, definition)]
        self.value_class = value_class

        super().__init__(fd=self.definition, user_types=user_types,
                         value_class=value_class)

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug('Added NormativeType: %s', self.type_name)
            for line in repr(self).split('\n'):
                logger.debug(line)

class NTScalarType(NormativeTypeBase):
    type_name = 'epics:nt/NTScalar:1.0'

    def __init__(self, scalar_t, *, has_descriptor=True, has_alarm=True,
                 has_timestamp=True, has_display=True, has_control=True,
                 additional_fields=None):
        definition = [
            '{} value'.format(scalar_t),
        ]

        if has_descriptor:
            definition.append('string descriptor')

        if has_alarm:
            definition.append('alarm_t alarm')

        if has_timestamp:
            definition.append('time_t time')

        if has_display:
            definition.append('display_t display')

        if has_control:
            definition.append('control_t control')

        if additional_fields:
            definition.extend(additional_fields)

        super().__init__(definition)


class NTScalarArrayType(NormativeTypeBase):
    type_name = 'epics:nt/NTScalar:1.0'

    def __init__(self, scalar_t, *, has_descriptor=True, has_alarm=True,
                 has_timestamp=True, has_display=True, has_control=True,
                 additional_fields=None):
        definition = [
            '{}[] value'.format(scalar_t),
        ]

        if has_descriptor:
            definition.append('string descriptor')

        if has_alarm:
            definition.append('alarm_t alarm')

        if has_timestamp:
            definition.append('time_t time')

        if has_display:
            definition.append('display_t display')

        if has_control:
            definition.append('control_t control')

        if additional_fields:
            definition.extend(additional_fields)

        super().__init__(definition)


if __name__ == '__main__':
    logger.setLevel('DEBUG')
    logging.basicConfig()


basic_types = {}
intro.update_namespace_with_definitions(basic_types, basic_type_definitions,
                                        logger=logger)


nt_scalar_types = tuple(types.scalar_type_names) + ('string', )
NTScalar = {scalar_t: NTScalarType(scalar_t)
            for scalar_t in nt_scalar_types}
NTScalarArray = {scalar_t: NTScalarArrayType(scalar_t)
                 for scalar_t in nt_scalar_types}


if __name__ == '__main__':
    print(NTScalarArray['string'].new_flat_value_dict())
