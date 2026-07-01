from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse

from apps.hr.models import Employee
from .models import Document, DocumentVersion, DocumentTag, DocumentShare
from .forms import (
    DocumentUploadForm, 
    DocumentVersionUploadForm, 
    DocumentEditForm,
    ShareWithUsersForm,
    ShareWithGroupsForm
)
from .utils import get_visible_documents_for_user, get_user_permission_for_document


@login_required
def document_list(request):
    """Liste der fÃ¼r den User sichtbaren Dokumente (Meine Dokumente)."""
    try:
        employee = request.user.employee
    except (AttributeError, Employee.DoesNotExist):
        messages.warning(request, "No employee profile found.")
        return render(request, 'documents/document_list.html', {'documents': []})

    # Sichtbare Dokumente holen (ohne archivierte)
    documents = get_visible_documents_for_user(employee, include_archived=False)
    print(f"[LIST DEBUG] User {employee} sieht aktuell {documents.count()} nicht-archivierte Dokumente")

    # Einfache Suche nach Titel und Tags
    search_query = request.GET.get('q', '').strip()
    if search_query:
        documents = documents.filter(
            Q(title__icontains=search_query) |
            Q(tags__name__icontains=search_query)
        ).distinct()
        print(f"[LIST DEBUG] Nach Suche '{search_query}' noch {documents.count()} Dokumente")

    documents = documents.order_by('-created_at')

    context = {
        'documents': documents,
        'search_query': search_query,
        'document_count': documents.count(),
    }
    return render(request, 'documents/document_list.html', context)


@login_required
def document_upload(request):
    """Neues Dokument mit erster Version hochladen."""
    print("\n" + "="*70)
    print("[UPLOAD DEBUG] Neue Upload-Anfrage gestartet")
    print(f"[UPLOAD DEBUG] User: {request.user.username} (ID: {request.user.id})")

    try:
        employee = request.user.employee
        print(f"[UPLOAD DEBUG] Employee gefunden: {employee} (ID: {employee.id})")
    except (AttributeError, Employee.DoesNotExist):
        print("[UPLOAD DEBUG] FEHLER: Kein Employee-Profil gefunden!")
        messages.error(request, "No employee profile found.")
        return redirect('documents:document_list')

    if request.method == 'POST':
        print("[UPLOAD DEBUG] POST-Request erkannt")

        # Zeige was im FILES ankommt
        if request.FILES:
            for key, f in request.FILES.items():
                print(f"[UPLOAD DEBUG] FILES['{key}']: name={f.name}, size={f.size}, content_type={f.content_type}")
        else:
            print("[UPLOAD DEBUG] WARNUNG: request.FILES ist leer!")

        form = DocumentUploadForm(request.POST, request.FILES)
        print("[UPLOAD DEBUG] Formular initialisiert")

        if form.is_valid():
            print("[UPLOAD DEBUG] Form.is_valid() = True")
            print(f"[UPLOAD DEBUG] Cleaned data: {form.cleaned_data}")

            try:
                print("[UPLOAD DEBUG] Starte atomic Transaction...")
                with transaction.atomic():
                    # Datei einlesen
                    uploaded_file = form.cleaned_data['file']
                    file_content = uploaded_file.read()
                    print(f"[UPLOAD DEBUG] Datei eingelesen: {len(file_content)} Bytes")

                    # Tags verarbeiten (nur fÃ¼r diesen User)
                    tag_names = form.cleaned_data.get('tags', [])
                    print(f"[UPLOAD DEBUG] Tags aus Formular: {tag_names}")
                    tags = []
                    for name in tag_names:
                        tag, created = DocumentTag.objects.get_or_create(
                            name=name,
                            created_by=employee
                        )
                        tags.append(tag)
                        print(f"[UPLOAD DEBUG]   Tag '{name}' {'neu angelegt' if created else 'existierte bereits'}")

                    # Erste Version erstellen
                    print("[UPLOAD DEBUG] Erstelle DocumentVersion...")
                    version = DocumentVersion.objects.create(
                        document=None,
                        version_number=1,
                        file=file_content,
                        original_filename=uploaded_file.name,
                        uploaded_by=employee,
                        comment="Erste Version"
                    )
                    print(f"[UPLOAD DEBUG] DocumentVersion erstellt mit ID {version.id}")

                    # Dokument erstellen
                    print("[UPLOAD DEBUG] Erstelle Document...")
                    document = Document.objects.create(
                        title=form.cleaned_data['title'],
                        description=form.cleaned_data['description'],
                        current_version=version,
                        created_by=employee,
                    )
                    print(f"[UPLOAD DEBUG] Document erstellt mit ID {document.id}")

                    # Version mit Dokument verknÃ¼pfen
                    version.document = document
                    version.save()
                    print("[UPLOAD DEBUG] Version mit Document verknÃ¼pft")

                    # Tags zuordnen
                    document.tags.set(tags)
                    print(f"[UPLOAD DEBUG] {len(tags)} Tags zugeordnet")

                    # Standard-Freigabe
                    print("[UPLOAD DEBUG] Erstelle DocumentShare...")
                    DocumentShare.objects.create(
                        document=document,
                        share_type='user',
                        shared_with_user=employee,
                        permission='manager',
                        shared_by=employee
                    )
                    print("[UPLOAD DEBUG] DocumentShare erstellt")

                    print(f"[UPLOAD DEBUG] ERFOLG! Dokument ID {document.id} wurde gespeichert.")
                    messages.success(request, f"Dokument „{document.title}“ wurde erfolgreich hochgeladen.")
                    return redirect('documents:document_list')

            except Exception as e:
                print(f"[UPLOAD DEBUG] !!! EXCEPTION !!!")
                print(f"[UPLOAD DEBUG] Exception Type: {type(e).__name__}")
                print(f"[UPLOAD DEBUG] Exception Message: {str(e)}")
                import traceback
                traceback.print_exc()
                messages.error(request, f"Fehler beim Hochladen: {str(e)}")

        else:
            print("[UPLOAD DEBUG] Form.is_valid() = False")
            print(f"[UPLOAD DEBUG] Form errors: {form.errors}")
            for field, errors in form.errors.items():
                print(f"[UPLOAD DEBUG]   â†’ Feld '{field}': {errors}")

            if 'file' in form.errors:
                messages.warning(request, "Es gab ein Problem mit der ausgewählten Datei. Bitte wähle sie erneut aus.")
            else:
                messages.error(request, "Bitte korrigiere die Fehler im Formular.")

    else:
        form = DocumentUploadForm()
        print("[UPLOAD DEBUG] GET-Request â†’ zeige leeres Formular")

    return render(request, 'documents/document_upload.html', {'form': form})


@login_required
def document_detail(request, pk):
    """Detailansicht eines Dokuments (aktuelle Version)."""
    try:
        employee = request.user.employee
    except (AttributeError, Employee.DoesNotExist):
        messages.error(request, "No employee profile found.")
        return redirect('documents:document_list')

    try:
        document = Document.objects.select_related(
            'current_version', 'created_by', 'current_version__uploaded_by'
        ).prefetch_related('tags', 'versions', 'versions__uploaded_by').get(pk=pk)
    except Document.DoesNotExist:
        messages.error(request, "Document not found.")
        return redirect('documents:document_list')

    permission = get_user_permission_for_document(employee, document)

    if not permission:
        messages.error(request, "You do not have permission to view this document.")
        return redirect('documents:document_list')

    can_edit = permission in ['editor', 'manager']
    can_manage = permission == 'manager'

    current_version = document.current_version
    filename_lower = current_version.original_filename.lower()
    is_image = filename_lower.endswith(('.png', '.jpg', '.jpeg'))

    context = {
        'document': document,
        'current_version': current_version,
        'permission': permission,
        'can_edit': can_edit,
        'can_manage': can_manage,
        'is_image': is_image,
    }
    return render(request, 'documents/document_detail.html', context)


@login_required
def document_download(request, version_pk):
    """Download einer bestimmten Version (als Datei)."""
    from django.http import HttpResponse

    try:
        employee = request.user.employee
    except (AttributeError, Employee.DoesNotExist):
        return redirect('documents:document_list')

    try:
        version = DocumentVersion.objects.select_related('document').get(pk=version_pk)
    except DocumentVersion.DoesNotExist:
        messages.error(request, "Version nicht gefunden.")
        return redirect('documents:document_list')

    permission = get_user_permission_for_document(employee, version.document)

    if not permission:
        messages.error(request, "Keine Berechtigung zum Herunterladen.")
        return redirect('documents:document_list')

    # Datei als Download serven
    response = HttpResponse(version.file, content_type='application/octet-stream')
    response['Content-Disposition'] = f'attachment; filename="{version.original_filename}"'
    return response


@login_required
def document_preview(request, version_pk):
    """Datei inline im Browser anzeigen (z.B. PDF oder Bild)."""
    from django.http import HttpResponse

    try:
        employee = request.user.employee
    except (AttributeError, Employee.DoesNotExist):
        return redirect('documents:document_list')

    try:
        version = DocumentVersion.objects.select_related('document').get(pk=version_pk)
    except DocumentVersion.DoesNotExist:
        messages.error(request, "Version nicht gefunden.")
        return redirect('documents:document_list')

    permission = get_user_permission_for_document(employee, version.document)

    if not permission:
        messages.error(request, "Keine Berechtigung, diese Datei anzusehen.")
        return redirect('documents:document_list')

    # Korrekten Content-Type setzen
    content_type = 'application/pdf'
    if version.original_filename.lower().endswith('.png'):
        content_type = 'image/png'
    elif version.original_filename.lower().endswith(('.jpg', '.jpeg')):
        content_type = 'image/jpeg'

    # Datei inline serven (im Browser anzeigen statt herunterladen)
    response = HttpResponse(version.file, content_type=content_type)
    response['Content-Disposition'] = f'inline; filename="{version.original_filename}"'
    return response


@login_required
def document_edit(request, pk):
    """Metadaten eines Dokuments bearbeiten (Titel, Beschreibung, Tags)."""
    try:
        employee = request.user.employee
    except (AttributeError, Employee.DoesNotExist):
        messages.error(request, "No employee profile found.")
        return redirect('documents:document_list')

    try:
        document = Document.objects.prefetch_related('tags').get(pk=pk)
    except Document.DoesNotExist:
        messages.error(request, "Document not found.")
        return redirect('documents:document_list')

    permission = get_user_permission_for_document(employee, document)

    if permission not in ['editor', 'manager']:
        messages.error(request, "Du hast keine Berechtigung, dieses Dokument zu bearbeiten.")
        return redirect('documents:document_detail', pk=pk)

    # Aktuelle Tags als kommagetrennten String vorbereiten
    current_tags = ", ".join([tag.name for tag in document.tags.filter(created_by=employee)])

    if request.method == 'POST':
        form = DocumentEditForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Metadaten aktualisieren
                    document.title = form.cleaned_data['title']
                    document.description = form.cleaned_data['description']

                    # Tags aktualisieren
                    tag_names = form.cleaned_data.get('tags', [])
                    new_tags = []
                    for name in tag_names:
                        tag, created = DocumentTag.objects.get_or_create(
                            name=name,
                            created_by=employee
                        )
                        new_tags.append(tag)
                    document.tags.set(new_tags)

                    document.save()

                    messages.success(request, "Metadaten wurden erfolgreich aktualisiert.")
                    return redirect('documents:document_detail', pk=pk)

            except Exception as e:
                messages.error(request, f"Fehler beim Speichern: {str(e)}")
        else:
            messages.error(request, "Bitte korrigiere die Fehler im Formular.")
    else:
        # Formular mit aktuellen Werten vorbelegen
        form = DocumentEditForm(initial={
            'title': document.title,
            'description': document.description,
            'tags': current_tags
        })

    context = {
        'document': document,
        'form': form,
    }
    return render(request, 'documents/document_edit.html', context)


@login_required
def document_manage_shares(request, pk):
    """Manage sharing permissions for a document."""
    try:
        employee = request.user.employee
    except (AttributeError, Employee.DoesNotExist):
        messages.error(request, "No employee profile found.")
        return redirect('documents:document_list')

    try:
        document = Document.objects.get(pk=pk)
    except Document.DoesNotExist:
        messages.error(request, "Document not found.")
        return redirect('documents:document_list')

    permission = get_user_permission_for_document(employee, document)

    if permission != 'manager':
        messages.error(request, "Only managers can manage shares for this document.")
        return redirect('documents:document_detail', pk=pk)

    current_shares = document.shares.select_related(
        'shared_with_user', 'shared_with_group'
    ).order_by('share_type', 'permission')

    user_share_form = ShareWithUsersForm()
    group_share_form = ShareWithGroupsForm()

    if request.method == 'POST':
        # Add shares with users
        if 'add_user_shares' in request.POST:
            user_share_form = ShareWithUsersForm(request.POST)
            if user_share_form.is_valid():
                users = user_share_form.cleaned_data['users']
                perm = user_share_form.cleaned_data['permission']
                sig_req = user_share_form.cleaned_data.get('signature_requirement', '')
                added = 0
                for user in users:
                    obj, created = DocumentShare.objects.get_or_create(
                        document=document,
                        share_type='user',
                        shared_with_user=user,
                        defaults={
                            'permission': perm,
                            'shared_by': employee,
                            'signature_requirement': sig_req
                        }
                    )
                    if created:
                        added += 1
                    else:
                        updated = False
                        if obj.permission != perm:
                            obj.permission = perm
                            updated = True
                        if obj.signature_requirement != sig_req:
                            obj.signature_requirement = sig_req
                            updated = True
                        if updated:
                            obj.save()
                            added += 1
                messages.success(request, f"Shares updated for {added} user(s).")
                return redirect('documents:document_manage_shares', pk=pk)
            else:
                messages.error(request, "Please correct the errors in the user sharing form.")

        # Add shares with groups
        elif 'add_group_shares' in request.POST:
            group_share_form = ShareWithGroupsForm(request.POST)
            if group_share_form.is_valid():
                groups = group_share_form.cleaned_data['groups']
                perm = group_share_form.cleaned_data['permission']
                sig_req = group_share_form.cleaned_data.get('signature_requirement', '')
                added = 0
                for grp in groups:
                    obj, created = DocumentShare.objects.get_or_create(
                        document=document,
                        share_type='group',
                        shared_with_group=grp,
                        defaults={
                            'permission': perm,
                            'shared_by': employee,
                            'signature_requirement': sig_req
                        }
                    )
                    if created:
                        added += 1
                    else:
                        updated = False
                        if obj.permission != perm:
                            obj.permission = perm
                            updated = True
                        if obj.signature_requirement != sig_req:
                            obj.signature_requirement = sig_req
                            updated = True
                        if updated:
                            obj.save()
                            added += 1
                messages.success(request, f"Shares updated for {added} group(s).")
                return redirect('documents:document_manage_shares', pk=pk)
            else:
                messages.error(request, "Please correct the errors in the group sharing form.")

        # Delete a share
        elif 'delete_share' in request.POST:
            share_id = request.POST.get('delete_share')
            try:
                share = DocumentShare.objects.get(id=share_id, document=document)
                share.delete()
                messages.success(request, "Share removed successfully.")
            except DocumentShare.DoesNotExist:
                messages.error(request, "Share not found.")
            return redirect('documents:document_manage_shares', pk=pk)

        # Update permission of an existing share
        elif 'update_permission' in request.POST:
            share_id = request.POST.get('share_id')
            new_permission = request.POST.get('permission')
            try:
                share = DocumentShare.objects.get(id=share_id, document=document)
                if new_permission in ['viewer', 'editor', 'manager']:
                    share.permission = new_permission
                    share.save()
                    messages.success(request, "Permission updated.")
            except DocumentShare.DoesNotExist:
                messages.error(request, "Share not found.")
            return redirect('documents:document_manage_shares', pk=pk)

    current_version = document.current_version

    context = {
        'document': document,
        'current_shares': current_shares,
        'user_share_form': user_share_form,
        'group_share_form': group_share_form,
        'current_version': current_version,
    }
    return render(request, 'documents/document_manage_shares.html', context)


@login_required
def document_upload_version(request, pk):
    """Neue Version zu einem bestehenden Dokument hochladen."""
    try:
        employee = request.user.employee
    except (AttributeError, Employee.DoesNotExist):
        messages.error(request, "No employee profile found.")
        return redirect('documents:document_list')

    try:
        document = Document.objects.get(pk=pk)
    except Document.DoesNotExist:
        messages.error(request, "Document not found.")
        return redirect('documents:document_list')

    permission = get_user_permission_for_document(employee, document)

    if permission not in ['editor', 'manager']:
        messages.error(request, "Du hast keine Berechtigung, eine neue Version hochzuladen.")
        return redirect('documents:document_detail', pk=pk)

    if request.method == 'POST':
        form = DocumentVersionUploadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    uploaded_file = form.cleaned_data['file']
                    file_content = uploaded_file.read()

                    # NÃ¤chste Versionsnummer ermitteln
                    last_version = document.versions.order_by('-version_number').first()
                    next_version_number = (last_version.version_number + 1) if last_version else 1

                    # Neue Version erstellen
                    new_version = DocumentVersion.objects.create(
                        document=document,
                        version_number=next_version_number,
                        file=file_content,
                        original_filename=uploaded_file.name,
                        uploaded_by=employee,
                        comment=form.cleaned_data.get('comment', '')
                    )

                    # Aktuelle Version aktualisieren
                    document.current_version = new_version
                    document.save()

                    messages.success(
                        request,
                        f"Neue Version {next_version_number} wurde erfolgreich hochgeladen."
                    )
                    return redirect('documents:document_detail', pk=pk)

            except Exception as e:
                messages.error(request, f"Fehler beim Hochladen der neuen Version: {str(e)}")
        else:
            messages.error(request, "Bitte korrigiere die Fehler im Formular.")
    else:
        form = DocumentVersionUploadForm()

    context = {
        'document': document,
        'form': form,
    }
    return render(request, 'documents/document_upload_version.html', context)


