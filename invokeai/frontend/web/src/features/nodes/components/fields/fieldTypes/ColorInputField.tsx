import { useAppDispatch } from 'app/store/storeHooks';
import { fieldColorValueChanged } from 'features/nodes/store/nodesSlice';
import {
  ColorInputFieldTemplate,
  ColorInputFieldValue,
} from 'features/nodes/types/types';
import { memo } from 'react';
import { RgbaColor, RgbaColorPicker } from 'react-colorful';
import { FieldComponentProps } from './types';

const ColorInputFieldComponent = (
  props: FieldComponentProps<ColorInputFieldValue, ColorInputFieldTemplate>
) => {
  const { nodeId, field } = props;

  const dispatch = useAppDispatch();

  const handleValueChanged = (value: RgbaColor) => {
    dispatch(fieldColorValueChanged({ nodeId, fieldName: field.name, value }));
  };

  return (
    <RgbaColorPicker
      className="nodrag"
      color={field.value}
      onChange={handleValueChanged}
    />
  );
};

export default memo(ColorInputFieldComponent);