"""Standard purchase catalog item form with optional image upload."""
import io

from django import forms
from django.core.exceptions import ValidationError
from PIL import Image as PILImage

from apps.tasks.models import StandardPurchaseItem


# ---------------------------------------------------------------------------
# Standard purchase items (catalog)
# ---------------------------------------------------------------------------
MAX_STANDARD_IMAGE_SIZE_MB = 5
THUMBNAIL_SIZE = (120, 120)


class StandardPurchaseItemForm(forms.ModelForm):
    """Form for creating/editing StandardPurchaseItem with optional image upload."""

    image = forms.FileField(
        label="Product Image (optional)",
        required=False,
        widget=forms.ClearableFileInput(attrs={'class': 'form-control'}),
        help_text=f"Max {MAX_STANDARD_IMAGE_SIZE_MB} MB. Will be shown as small thumbnail in selection lists."
    )

    class Meta:
        model = StandardPurchaseItem
        fields = [
            'supplier', 'product_name', 'product_description',
            'link_to_product', 'order_number', 'unit_price'
        ]
        widgets = {
            'product_description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'link_to_product': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://...'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            if field != 'image' and hasattr(self.fields[field].widget, 'attrs'):
                self.fields[field].widget.attrs.setdefault('class', 'form-control')

        # Make some fields required for usability
        self.fields['supplier'].required = True
        self.fields['product_name'].required = True
        self.fields['unit_price'].required = True

    def clean_image(self):
        uploaded_file = self.cleaned_data.get('image')
        if not uploaded_file:
            return None

        # Size check
        max_bytes = MAX_STANDARD_IMAGE_SIZE_MB * 1024 * 1024
        if uploaded_file.size > max_bytes:
            raise ValidationError(f"Image too large. Maximum allowed size is {MAX_STANDARD_IMAGE_SIZE_MB} MB.")

        # Basic image validation + thumbnail generation
        try:
            img = PILImage.open(uploaded_file)
            img.verify()  # Check it's a valid image
            uploaded_file.seek(0)  # Reset after verify

            # Create thumbnail
            img = PILImage.open(uploaded_file)
            img.thumbnail(THUMBNAIL_SIZE, PILImage.LANCZOS)

            # Convert to RGB if necessary (for PNG with alpha etc.)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            thumb_io = io.BytesIO()
            img.save(thumb_io, format='JPEG', quality=85, optimize=True)
            thumb_io.seek(0)

            self.cleaned_data['thumbnail_data'] = thumb_io.getvalue()
            self.cleaned_data['image_content_type'] = uploaded_file.content_type or 'image/jpeg'

            # Reset original file pointer for later reading
            uploaded_file.seek(0)
            return uploaded_file

        except Exception as e:
            raise ValidationError(f"Invalid image file: {str(e)}")

    def save(self, commit=True):
        instance = super().save(commit=False)

        uploaded_file = self.cleaned_data.get('image')
        if uploaded_file:
            instance.image = uploaded_file.read()
            instance.image_filename = uploaded_file.name
            instance.image_content_type = self.cleaned_data.get('image_content_type', 'image/jpeg')
            instance.thumbnail = self.cleaned_data.get('thumbnail_data')

        if commit:
            instance.save()
        return instance

