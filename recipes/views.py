from django.core.exceptions import ValidationError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.urls import reverse

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required

from django.db.models import Avg, Count, Q

from recipes.models import Category, Recipe, Review, UserProfile
from recipes.forms import UserForm, UserProfileForm, RecipeForm, ReviewForm, SearchForm

from datetime import timedelta


def home(request):
    category_list = Category.objects.annotate(number_of_recipes=Count('recipe')).order_by('-number_of_recipes')[:4]
    recipe_list = Recipe.objects.annotate(average_rating=Avg('review__rating')).order_by('-average_rating')[:4]

    context_dict = {'categories': category_list, 'recipes': recipe_list}

    return render(request, 'recipes/home.html', context=context_dict)


def categories(request):
    category_list = Category.objects.annotate(number_of_recipes=Count('recipe')).order_by('-number_of_recipes')

    context_dict = {'categories': category_list}

    return render(request, 'recipes/categories.html', context=context_dict)


def show_category(request, category_name_slug):
    context_dict = {}

    category = get_object_or_404(Category, slug=category_name_slug)
    recipes = Recipe.objects.annotate(average_rating=Avg('review__rating')).filter(category=category).distinct()

    context_dict['category'] = category
    context_dict['recipes'] = recipes

    return render(request, 'recipes/category.html', context=context_dict)


def show_results(request):
    req = request.GET.get('q', default="")
    req_words = set(req.split())

    form = SearchForm(request.GET)
    context_dict = {"req": req, "form": form, "results": None}

    query = Q()
    for word in req_words:
        query |= Q(title__icontains=word) | Q(ingredients__icontains=word) | Q(tags__icontains=word)

    if form.is_valid():
        categories = form.cleaned_data['category']
        time = form.cleaned_data['time']
        author = form.cleaned_data['author']
        sort = form.cleaned_data['sort']

        if categories.exists():
            query &= Q(category__in=categories)

        if time:
            query &= Q(cooking_time__lte=time)

        if author:
            query &= Q(author=User.objects.get(userprofile=author))

        results = Recipe.objects.filter(query).annotate(average_rating=Avg('review__rating'))

        sorts = {
            'rd': '-average_rating',
            'ra': 'average_rating',
            'aa': 'title',
            'ad': '-title'
        }
        if sort:
            results = results.order_by(sorts[sort])

        context_dict["results"] = results

    return render(request, 'recipes/results.html', context=context_dict)


def user_login(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(username=username, password=password)

        if user:
            if user.is_active:
                login(request, user)
                return redirect(reverse('recipes:home'))
            else:
                context_dict = {'message': 'Your Food For Thought account is disabled'}
        else:
            print(f"Invalid login details: {username}, {password}")
            context_dict = {'message': 'Invalid login details given, please enter valid details'}

        return render(request, "recipes/login.html", context=context_dict)

    else:
        context_dict = {'message': None}
        return render(request, "recipes/login.html", context=context_dict)


@login_required
def user_logout(request):
    logout(request)
    return redirect(reverse('recipes:home'))


def sign_up(request):
    registered = False

    if request.method == 'POST':
        user_form = UserForm(request.POST)
        profile_form = UserProfileForm(request.POST, request.FILES)

        if user_form.is_valid() and profile_form.is_valid():
            user = user_form.save()

            user.set_password(user.password)
            user.save()

            profile = profile_form.save(commit=False)
            profile.user = user

            if 'picture' in request.FILES:
                profile.picture = request.FILES['picture']

            profile.save()

            registered = True

    else:
        user_form = UserForm()
        profile_form = UserProfileForm()

    context_dict = {'user_form': user_form, 'profile_form': profile_form, 'registered': registered}

    return render(request, 'recipes/signup.html', context=context_dict)


def show_recipe(request, user_id, recipe_name_slug):
    context_dict = {}

    recipe = get_object_or_404(Recipe, slug=recipe_name_slug, author=User.objects.get(id=user_id))
    average_rating = Review.objects.filter(recipe=recipe).aggregate(Avg('rating'))['rating__avg']
    reviews = Review.objects.filter(recipe_id=recipe.id)

    context_dict['recipe'] = recipe
    context_dict['average_rating'] = average_rating
    context_dict['reviews'] = reviews
    if request.user.is_authenticated and not Review.objects.filter(author=request.user,
                                                                   recipe=recipe).exists() and not recipe.author == request.user:
        form = ReviewForm()

        if request.method == "POST":
            form = ReviewForm(request.POST)

            if form.is_valid():
                review = form.save(commit=False)
                review.author = request.user
                review.recipe = recipe
                review.save()

                return redirect(reverse('recipes:show_recipe', args=[user_id, recipe_name_slug]))
            else:
                print(form.errors)

        context_dict['review_form'] = form

    return render(request, 'recipes/recipe.html', context=context_dict)


@login_required
def show_user_account(request, msg=None):
    if msg is None:
        current_user = request.user

        current_user_profile = UserProfile.objects.get(user=current_user)

        saved_recipes_ratings = current_user_profile.saved.annotate(average_rating=Avg('review__rating')).order_by('-average_rating')[:4]

        written_recipes = Recipe.objects.filter(author=current_user).annotate(average_rating=Avg('review__rating')).order_by('-average_rating')[:4]

        written_reviews = Review.objects.filter(author=current_user)[:4]

        context_dict = {"current_user": current_user_profile, "saved_recipes": saved_recipes_ratings,
                        "written_recipes": written_recipes,
                        "written_reviews": written_reviews}

        return render(request, 'recipes/my_account.html', context=context_dict)

    else:
        return HttpResponse(msg)


@login_required
def add_recipe(request):
    form = RecipeForm()

    if request.method == "POST":
        form = RecipeForm(request.POST, request.FILES)

        if form.is_valid():
            recipe = form.save(commit=False)
            recipe.author = request.user

            if 'image' in request.FILES:
                recipe.image = request.FILES['image']

            recipe.save()

            recipe.category.add(*form.cleaned_data['category'])

            return redirect(reverse('recipes:show_user_account'))
        else:
            print(form.errors)

    context_dict = {'form': form}
    return render(request, 'recipes/add_recipe.html', context=context_dict)


@login_required
def show_user_recipes(request):
    current_user = request.user

    written_recipes = Recipe.objects.filter(author=current_user)

    written_recipes = written_recipes.annotate(average_rating=Avg('review__rating'))

    context_dict = {'written_recipes': written_recipes}

    return render(request, 'recipes/my_recipes.html', context=context_dict)


@login_required
def show_user_reviews(request):
    current_user = request.user

    written_reviews = Review.objects.filter(author=current_user)

    context_dict = {'written_reviews': written_reviews}

    return render(request, 'recipes/my_reviews.html', context=context_dict)


@login_required
def show_user_saved_recipes(request):
    current_user = request.user

    current_user_profile = UserProfile.objects.get(user=current_user)

    saved_recipes = current_user_profile.saved.annotate(average_rating=Avg('review__rating')).order_by(
        '-average_rating')

    context_dict = {'saved_recipes': saved_recipes}

    return render(request, 'recipes/saved_recipes.html', context=context_dict)


def show_non_user_account(request, user_id):
    user = get_object_or_404(User, id=user_id)
    if user == request.user:
        return redirect(reverse('recipes:show_user_account'))

    user_profile = UserProfile.objects.get(user=user)

    written_recipes = Recipe.objects.filter(author=user).annotate(average_rating=Avg('review__rating')).order_by('-average_rating')[:4]

    written_reviews = Review.objects.filter(author=user)[:3]

    context_dict = {"account_user": user, "written_recipes": written_recipes,
                    "written_reviews": written_reviews, "user_profile": user_profile}
    return render(request, 'recipes/others_account.html', context=context_dict)


def show_non_user_recipes(request, user_id):
    user = get_object_or_404(User, id=user_id)
    written_recipes = Recipe.objects.filter(author=user).annotate(average_rating=Avg('review__rating')).order_by('-average_rating')[:4]

    context_dict = {'written_recipes': written_recipes, "account_user": user}

    return render(request, 'recipes/others_recipes.html', context=context_dict)


@login_required
def edit_account(request):
    edited = False

    user_profile = UserProfile.objects.get(user=request.user)

    if request.method == 'POST':
        user_form = UserForm(request.POST, instance=request.user)
        profile_form = UserProfileForm(request.POST, request.FILES, instance=user_profile)

        if user_form.is_valid() and profile_form.is_valid():
            user = user_form.save()

            user.set_password(user.password)
            user.first_name = user_form.cleaned_data["firstname"]
            user.last_name = user_form.cleaned_data["lastname"]
            user.save()

            profile = profile_form.save(commit=False)
            profile.user = user

            if 'picture' in request.FILES:
                profile.picture = request.FILES['picture']

            profile.save()

            edited = True
    else:
        user_form = UserForm(instance=request.user)
        profile_form = UserProfileForm(instance=user_profile)

    context_dict = {'user_form': user_form, 'profile_form': profile_form, 'edited': edited, "user_profile": user_profile}

    return render(request, 'recipes/update_profile.html', context=context_dict)


@login_required
def edit_review(request, review_id):
    review = Review.objects.get(id=review_id)

    if request.method == "POST":
        form = ReviewForm(request.POST, instance=review)

        if form.is_valid():
            review = form.save(commit=False)
            review.author = request.user
            review.recipe = review.recipe
            review.save()

            return redirect(reverse('recipes:show_user_account'))
        else:
            print(form.errors)

    else:
        form = ReviewForm(instance=review)

    context_dict = {'review_form': form, 'review': review, 'recipe': review.recipe, 'values': ["5", "4", "3", "2", "1"],
                    'checked_val': str(review.rating)}

    return render(request, 'recipes/edit_review.html', context=context_dict)


@login_required
def edit_recipe(request, recipe_id):
    recipe = Recipe.objects.get(id=recipe_id, author=request.user)

    if request.method == "POST":
        form = RecipeForm(request.POST, request.FILES, instance=recipe)

        if form.is_valid():
            recipe = form.save(commit=False)
            recipe.author = request.user

            if 'image' in request.FILES:
                recipe.image = request.FILES['image']

            recipe.save()

            recipe.category.clear()

            recipe.category.add(*form.cleaned_data['category'])

            return redirect(reverse('recipes:show_user_account'))
        else:
            print(form.errors)
    else:
        form = RecipeForm(instance=recipe)

    context_dict = {'form': form, 'recipe': recipe}
    return render(request, 'recipes/edit_recipe_page.html', context=context_dict)


@login_required
def delete_account(request):
    is_deleted = False

    try:
        current_user = request.user
        logout(request)
        current_user.delete()
        is_deleted = True

    except Exception as e:
        show_user_account(request, "Could not delete account. Encountered following error: " + e)

    context_dict = {'deleted': is_deleted}

    return render(request, 'recipes/my_account.html', context=context_dict)


@login_required
def delete_review(request, review_id):
    try:
        review = Review.objects.get(id=review_id, author=request.user)
        review.delete()

    except Exception as e:
        show_user_account(request, "Could not delete review. Encountered following error: " + e)

    return JsonResponse({
        'response': """
        <div class='card-body text-start'>
        <h5 class='card-title'>Review Deleted</h5>
        </div>""",
        'id': f"#review{review_id}"})


@login_required
def delete_recipe(request, recipe_id):
    try:
        recipe = Recipe.objects.get(id=recipe_id, author=request.user)
        recipe.delete()

    except Exception as e:
        show_user_account(request, "Could not delete recipe. Encountered following error: " + e)

    if request.is_ajax():
        return JsonResponse({
            'response': """
            <div class='card-body text-start'>
            <h5 class='card-title'>Recipe Deleted</h5>
            </div>""",
            'id': f"#recipe{recipe_id}"})

    else:
        return redirect(reverse('recipes:show_user_account'))


@login_required
def toggle_save_recipe(request, recipe_id):
    try:
        recipe = get_object_or_404(Recipe, id=recipe_id)
        user_profile = request.user.userprofile
        if recipe in user_profile.saved.all():
            user_profile.saved.remove(recipe)
        else:
            user_profile.saved.add(recipe)

    except Exception as e:
        show_user_account(request, "Could not unsave recipe. Encountered following error: " + e)

    return JsonResponse({
        'response': render_to_string('recipes/toggle_save_button.html', request=request, context={"recipe": recipe}),
        'id': f"#saveRecipeButton{recipe_id}"})

def fetch_cats(request):
    search = request.GET.get('q', default="")
    res = {"results": []}
    if search != "":
        cats = Category.objects.filter(name__icontains=search)[:3]
        for cat in cats:
            res["results"].append({"id": cat.id, "text": cat.name})                
    return JsonResponse(res)

def fetch_author(request):
    search = request.GET.get('q', default="")
    res = {"results": []}
    if search != "":
        users = User.objects.filter(username__icontains=search)[:3]
        for user in users:
            res["results"].append({"id": user.id, "text": user.username})                
    return JsonResponse(res)
